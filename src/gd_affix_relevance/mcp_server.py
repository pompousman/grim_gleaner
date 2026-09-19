"""Model Context Protocol (MCP) stdio server for local integrations.

This module exposes the same deterministic operations as the localhost HTTP
API (``automation_server``) over MCP's stdio transport: newline-delimited
JSON-RPC 2.0 on stdin/stdout.  It is dependency-free and makes Grim Gleaner
directly usable by MCP clients such as desktop assistants and IDE agents
without any vendor account or network access.

Only the server subset Grim Gleaner needs is implemented: ``initialize``,
``ping``, ``tools/list``, and ``tools/call``.  Unknown requests receive
standard JSON-RPC errors, and notifications are silently acknowledged.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from gd_affix_relevance import __version__
from gd_affix_relevance.automation import profile_json_schema
from gd_affix_relevance.automation_server import AutomationService
from gd_affix_relevance.catalog import CatalogBundle

MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SERVER_NAME = "grim-gleaner"

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


def _text_result(payload: object, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False),
            }
        ],
        "isError": is_error,
    }


def _error_response(
    request_id: object, code: int, message: str
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _result_response(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


_PROFILE_OBJECT = {
    "type": "object",
    "description": (
        "A Grim Gleaner build profile matching the profile schema; obtain "
        "valid IDs from the get_profile_context tool."
    ),
}

_MASTERIES_ARGUMENT = {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Optional mastery IDs (e.g. playerclass05); when given, only those "
        "skill trees are included in the context."
    ),
}

TOOL_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "get_catalog_status",
        "description": (
            "Report the catalog game version and schema version used by "
            "this server."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_profile_schema",
        "description": (
            "Return the versioned JSON Schema every build profile must "
            "match before it can be validated or ranked."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_profile_context",
        "description": (
            "Return the provider-neutral discovery context: valid stat IDs, "
            "mastery and skill IDs, the weight scale, level bands, and "
            "workflow instructions. Start here when building a profile."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"masteries": _MASTERIES_ARGUMENT},
            "additionalProperties": False,
        },
    },
    {
        "name": "validate_profile",
        "description": (
            "Validate one build profile: shape, known stat/skill/mastery "
            "IDs, and mastery/skill relationships, with typo suggestions. "
            "A result with valid=false is a successful tool call, not an "
            "error."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"profile": _PROFILE_OBJECT},
            "required": ["profile"],
            "additionalProperties": False,
        },
    },
    {
        "name": "diff_profiles",
        "description": (
            "Compare two profiles semantically and return a stable, "
            "machine-readable change list suitable for review."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "before": _PROFILE_OBJECT,
                "after": _PROFILE_OBJECT,
            },
            "required": ["before", "after"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rank_profile",
        "description": (
            "Rank affixes, uniques, components, and augments per equipment "
            "slot for a validated profile. Each result explains its grade "
            "with matched stat weights, unmatched stats, and next-grade "
            "counterfactual hints."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile": _PROFILE_OBJECT,
                "kinds": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["affix", "unique", "component", "augment"],
                    },
                    "description": "Optional subset of result kinds.",
                },
                "slots": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional slot IDs or aliases such as ring, belt, "
                        "or helm; defaults to every slot."
                    ),
                },
                "limit_per_slot": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "Maximum matches per slot and kind.",
                },
                "minimum_grade": {
                    "type": "string",
                    "enum": ["S++", "S+", "S", "A", "B", "C", "D"],
                    "description": "Minimum grade for unique items.",
                },
            },
            "required": ["profile"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_catalog",
        "description": (
            "Search skills, affixes, and items by name or record ID to "
            "discover exact IDs for profiles."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "kind": {
                    "type": "string",
                    "enum": ["all", "skill", "affix", "item"],
                    "description": "Optional result kind filter.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
)

TOOL_NAMES = frozenset(tool["name"] for tool in TOOL_DEFINITIONS)


class McpToolbox:
    """Bind catalog-backed operations to MCP tool calls."""

    def __init__(self, catalog: CatalogBundle) -> None:
        self.service = AutomationService(catalog)

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [dict(tool) for tool in TOOL_DEFINITIONS]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_catalog_status":
            return _text_result(self.service.health())
        if name == "get_profile_schema":
            return _text_result(profile_json_schema())
        if name == "get_profile_context":
            masteries = arguments.get("masteries", [])
            if not isinstance(masteries, list) or not all(
                isinstance(mastery, str) for mastery in masteries
            ):
                raise ValueError("masteries must be a list of strings")
            return _text_result(self.service.context(tuple(masteries)))
        if name == "validate_profile":
            if "profile" not in arguments:
                raise ValueError("validate_profile requires a profile")
            return _text_result(self.service.validate(arguments["profile"]))
        if name == "diff_profiles":
            if "before" not in arguments or "after" not in arguments:
                raise ValueError("diff_profiles requires before and after")
            return _text_result(
                self.service.diff(
                    {
                        "before": arguments["before"],
                        "after": arguments["after"],
                    }
                )
            )
        if name == "rank_profile":
            if "profile" not in arguments:
                raise ValueError("rank_profile requires a profile")
            return _text_result(self.service.ranking(arguments))
        if name == "search_catalog":
            query = arguments.get("query")
            if not isinstance(query, str):
                raise ValueError("search_catalog requires a query string")
            kind = arguments.get("kind", "all")
            if not isinstance(kind, str):
                raise ValueError("search kind must be a string")
            limit = arguments.get("limit", 20)
            if isinstance(limit, bool) or not isinstance(limit, int):
                raise ValueError("search limit must be an integer")
            return _text_result(
                self.service.search(query, kind=kind, limit=limit)
            )
        raise ValueError(f"unknown tool: {name}")


def handle_message(
    payload: object,
    toolbox: McpToolbox,
) -> dict[str, Any] | None:
    """Process one decoded JSON-RPC message and return the response, if any.

    Returning ``None`` means the message was a notification (or an ignorable
    event) and must not be answered, per JSON-RPC 2.0.
    """

    if not isinstance(payload, dict):
        return _error_response(
            None, JSONRPC_INVALID_REQUEST, "request must be a JSON object"
        )
    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return _error_response(
            request_id,
            JSONRPC_INVALID_REQUEST,
            'request must include "jsonrpc": "2.0"',
        )
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        return _error_response(
            request_id, JSONRPC_INVALID_REQUEST, "request method must be a string"
        )
    if method.startswith("notifications/"):
        return None
    if "id" not in payload:
        # A message with a method but no id is a notification in JSON-RPC 2.0.
        return None
    params = payload.get("params", {})
    if not isinstance(params, dict):
        return _error_response(
            request_id, JSONRPC_INVALID_PARAMS, "request params must be an object"
        )

    if method == "initialize":
        client_version = params.get("protocolVersion")
        protocol_version = (
            client_version
            if isinstance(client_version, str) and client_version
            else MCP_PROTOCOL_VERSION
        )
        return _result_response(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": MCP_SERVER_NAME,
                    "version": __version__,
                },
            },
        )
    if method == "ping":
        return _result_response(request_id, {})
    if method == "tools/list":
        return _result_response(
            request_id, {"tools": toolbox.tool_definitions()}
        )
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or name not in TOOL_NAMES:
            return _error_response(
                request_id,
                JSONRPC_INVALID_PARAMS,
                f"unknown tool: {name!r}",
            )
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error_response(
                request_id,
                JSONRPC_INVALID_PARAMS,
                "tool arguments must be an object",
            )
        try:
            return _result_response(
                request_id, toolbox.call_tool(name, arguments)
            )
        except (TypeError, ValueError) as error:
            return _result_response(
                request_id, _text_result(f"error: {error}", is_error=True)
            )
    return _error_response(
        request_id, JSONRPC_METHOD_NOT_FOUND, f"method not found: {method}"
    )


def serve_stdio(
    catalog: CatalogBundle,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run the MCP stdio loop until stdin closes.

    The loop is deliberately defensive: a malformed line produces a parse
    error response instead of terminating the server, and stdout carries
    nothing except JSON-RPC messages (startup notes go to stderr).
    """

    reader = stdin if stdin is not None else sys.stdin
    writer = stdout if stdout is not None else sys.stdout
    toolbox = McpToolbox(catalog)

    for line in reader:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload: object = json.loads(stripped)
        except json.JSONDecodeError as error:
            response = _error_response(
                None, JSONRPC_PARSE_ERROR, f"parse error: {error}"
            )
        else:
            try:
                response = handle_message(payload, toolbox)
            except Exception as error:  # noqa: BLE001 - never kill the server
                response = _error_response(
                    None, JSONRPC_INTERNAL_ERROR, f"internal error: {error}"
                )
        if response is not None:
            writer.write(json.dumps(response, ensure_ascii=False) + "\n")
            writer.flush()
    return 0
