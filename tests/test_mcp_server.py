"""Tests for the MCP stdio server exposing the automation tools."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from gd_affix_relevance.catalog import CatalogBundle
from gd_affix_relevance.mcp_server import (
    MCP_SERVER_NAME,
    McpToolbox,
    handle_message,
    serve_stdio,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def toolbox() -> McpToolbox:
    catalog = CatalogBundle.load(PROJECT_ROOT / "artifacts" / "catalog")
    return McpToolbox(catalog)


def _request(
    toolbox: McpToolbox,
    method: str,
    params: dict | None = None,
    *,
    request_id: object = 1,
) -> dict:
    payload: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = handle_message(payload, toolbox)
    assert response is not None
    return response


def _tool_payload(response: dict) -> object:
    result = response["result"]
    assert result["isError"] is False
    return json.loads(result["content"][0]["text"])


def test_initialize_echoes_client_protocol_and_advertises_tools(
    toolbox: McpToolbox,
) -> None:
    response = _request(
        toolbox,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.0"},
        },
    )

    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == MCP_SERVER_NAME
    assert result["serverInfo"]["version"]


def test_initialize_defaults_protocol_version_when_client_omits_it(
    toolbox: McpToolbox,
) -> None:
    response = _request(toolbox, "initialize", {"capabilities": {}})

    assert response["result"]["protocolVersion"]


def test_ping_and_tools_list(toolbox: McpToolbox) -> None:
    assert _request(toolbox, "ping")["result"] == {}

    listed = _request(toolbox, "tools/list")["result"]["tools"]
    names = {tool["name"] for tool in listed}
    assert names == {
        "get_catalog_status",
        "get_profile_schema",
        "get_profile_context",
        "validate_profile",
        "diff_profiles",
        "rank_profile",
        "search_catalog",
    }
    for tool in listed:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"


def test_notifications_never_produce_responses(toolbox: McpToolbox) -> None:
    assert (
        handle_message(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            toolbox,
        )
        is None
    )
    assert (
        handle_message(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 7},
            },
            toolbox,
        )
        is None
    )


def test_malformed_messages_receive_jsonrpc_errors(toolbox: McpToolbox) -> None:
    not_an_object = handle_message([1, 2, 3], toolbox)
    assert not_an_object["error"]["code"] == -32600

    wrong_version = handle_message(
        {"jsonrpc": "1.0", "id": 1, "method": "ping"}, toolbox
    )
    assert wrong_version["error"]["code"] == -32600

    unknown_method = _request(toolbox, "resources/list")
    assert unknown_method["error"]["code"] == -32601


def test_context_and_schema_tools(toolbox: McpToolbox) -> None:
    context = _tool_payload(
        _request(
            toolbox,
            "tools/call",
            {
                "name": "get_profile_context",
                "arguments": {"masteries": ["playerclass05"]},
            },
        )
    )
    assert context["selected_masteries"] == ["playerclass05"]

    schema = _tool_payload(
        _request(
            toolbox,
            "tools/call",
            {"name": "get_profile_schema", "arguments": {}},
        )
    )
    assert schema["required"]


def test_validate_profile_tool_reports_invalid_profiles_as_results(
    toolbox: McpToolbox,
) -> None:
    payload = {
        "schema_version": 5,
        "name": "Broken",
        "level_band": "90+",
        "masteries": ["playerclass05", "playerclass08"],
        "skill_weights": {},
        "weights": {"nonexistent_stat": 4},
        "resistance_cap_enabled": False,
        "resistance_cap_weights": {},
        "excluded_conversion_sources": {},
    }

    response = _request(
        toolbox,
        "tools/call",
        {"name": "validate_profile", "arguments": {"profile": payload}},
    )

    # An invalid profile is a successful tool call carrying valid=false.
    assert response["result"]["isError"] is False
    validation = json.loads(response["result"]["content"][0]["text"])
    assert validation["valid"] is False
    assert "nonexistent_stat" in validation["errors"][0]["message"]


def test_rank_profile_tool_returns_explainable_ranking(
    toolbox: McpToolbox,
) -> None:
    payload = {
        "schema_version": 5,
        "name": "Lightning MCP",
        "level_band": "90+",
        "masteries": ["playerclass05", "playerclass08"],
        "skill_weights": {},
        "weights": {
            "flat_lightning_damage": 4,
            "lightning_damage_percent": 4,
        },
        "resistance_cap_enabled": False,
        "resistance_cap_weights": {},
        "excluded_conversion_sources": {},
    }

    ranking = _tool_payload(
        _request(
            toolbox,
            "tools/call",
            {
                "name": "rank_profile",
                "arguments": {
                    "profile": payload,
                    "kinds": ["affix"],
                    "slots": ["ring"],
                    "limit_per_slot": 2,
                },
            },
        )
    )

    assert ranking["protocol"] == "grim-gleaner-profile-ranking"
    prefixes = ranking["slots"]["ring"]["prefixes"]
    assert prefixes
    assert prefixes[0]["next_grade_hints"] is not None


def test_tool_argument_errors_are_tool_results_not_protocol_errors(
    toolbox: McpToolbox,
) -> None:
    response = _request(
        toolbox,
        "tools/call",
        {"name": "validate_profile", "arguments": {}},
    )

    assert response["result"]["isError"] is True
    assert "requires a profile" in response["result"]["content"][0]["text"]


def test_unknown_tool_is_an_invalid_params_error(toolbox: McpToolbox) -> None:
    response = _request(
        toolbox,
        "tools/call",
        {"name": "explode", "arguments": {}},
    )

    assert response["error"]["code"] == -32602


def test_diff_profiles_tool(toolbox: McpToolbox) -> None:
    before = {
        "schema_version": 5,
        "name": "Before",
        "level_band": "90+",
        "masteries": ["", ""],
        "skill_weights": {},
        "weights": {},
        "resistance_cap_enabled": False,
        "resistance_cap_weights": {},
        "excluded_conversion_sources": {},
    }
    after = dict(before)
    after = {
        **before,
        "name": "After",
        "weights": {"health": 4},
    }

    diff = _tool_payload(
        _request(
            toolbox,
            "tools/call",
            {
                "name": "diff_profiles",
                "arguments": {"before": before, "after": after},
            },
        )
    )

    assert diff["summary"]["changes"] == 2


def test_serve_stdio_handles_a_full_session(tmp_path: Path) -> None:
    import io

    catalog = CatalogBundle.load(PROJECT_ROOT / "artifacts" / "catalog")
    outgoing = io.StringIO()
    incoming = io.StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "t", "version": "0"},
                        },
                    }
                ),
                json.dumps(
                    {"jsonrpc": "2.0", "method": "notifications/initialized"}
                ),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "get_catalog_status",
                            "arguments": {},
                        },
                    }
                ),
                "   ",
                "{not json",
            ]
        )
        + "\n"
    )

    exit_code = serve_stdio(
        catalog, stdin=incoming, stdout=outgoing
    )

    assert exit_code == 0
    lines = [
        json.loads(line)
        for line in outgoing.getvalue().splitlines()
        if line.strip()
    ]
    assert len(lines) == 3  # notification produced no response
    assert lines[0]["result"]["serverInfo"]["name"] == MCP_SERVER_NAME
    assert lines[1]["result"]["isError"] is False
    assert lines[2]["error"]["code"] == -32700


def test_cli_serve_mcp_end_to_end_over_subprocess() -> None:
    script = (
        "from gd_affix_relevance.cli import main;"
        "import sys;"
        "sys.exit(main(['serve-mcp', '--catalog-root',"
        f" {str((PROJECT_ROOT / 'artifacts' / 'catalog').resolve())!r}]))"
    )
    process = subprocess.run(
        [sys.executable, "-c", script],
        input=(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                }
            )
            + "\n"
        ),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert process.returncode == 0
    response = json.loads(process.stdout.strip())
    assert response["id"] == 1
    tool_names = {tool["name"] for tool in response["result"]["tools"]}
    assert "rank_profile" in tool_names
