"""Dependency-free, localhost-first HTTP API for external integrations."""

from __future__ import annotations

import ipaddress
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from gd_affix_relevance.automation import (
    build_profile_context,
    compare_profiles,
    profile_json_schema,
    validate_profile_semantics,
)
from gd_affix_relevance.catalog import CatalogBundle
from gd_affix_relevance.profile_store import load_profile_payload
from gd_affix_relevance.ranking_export import (
    DEFAULT_LIMIT_PER_SLOT,
    DEFAULT_MINIMUM_GRADE,
    MAX_LIMIT_PER_SLOT,
    build_profile_ranking,
)

MAX_REQUEST_BYTES = 1_048_576


class AutomationService:
    """Pure request operations shared by HTTP handlers and tests."""

    def __init__(self, catalog: CatalogBundle) -> None:
        self.catalog = catalog

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "service": "grim-gleaner-automation",
            "game_version": self.catalog.manifest.game_version,
            "catalog_schema_version": self.catalog.manifest.schema_version,
        }

    def context(self, mastery_ids: tuple[str, ...]) -> dict[str, Any]:
        return build_profile_context(self.catalog, mastery_ids=mastery_ids)

    def validate(self, payload: object) -> dict[str, Any]:
        profile = load_profile_payload(payload)
        result = validate_profile_semantics(profile, self.catalog)
        return result.as_dict()

    def diff(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("diff request must be an object")
        if "before" not in payload or "after" not in payload:
            raise ValueError("diff request requires before and after profiles")
        before = load_profile_payload(payload["before"])
        after = load_profile_payload(payload["after"])
        return compare_profiles(before, after).as_dict()

    def ranking(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("ranking request must be an object")
        if "profile" not in payload:
            raise ValueError("ranking request requires a profile")
        profile = load_profile_payload(payload["profile"])
        semantics = validate_profile_semantics(profile, self.catalog)
        if not semantics.valid:
            raise ValueError(
                "ranking request profile failed validation: "
                + "; ".join(
                    f"{diagnostic.path}: {diagnostic.message}"
                    for diagnostic in semantics.errors
                )
            )
        kinds = payload.get("kinds", [])
        if not isinstance(kinds, list) or not all(
            isinstance(kind, str) for kind in kinds
        ):
            raise ValueError("ranking request kinds must be a list of strings")
        slots = payload.get("slots", [])
        if not isinstance(slots, list) or not all(
            isinstance(slot, str) for slot in slots
        ):
            raise ValueError("ranking request slots must be a list of strings")
        limit = payload.get("limit_per_slot", DEFAULT_LIMIT_PER_SLOT)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit_per_slot must be an integer")
        if not 1 <= limit <= MAX_LIMIT_PER_SLOT:
            raise ValueError(
                f"limit_per_slot must be between 1 and {MAX_LIMIT_PER_SLOT}"
            )
        minimum_grade = payload.get("minimum_grade", DEFAULT_MINIMUM_GRADE)
        if not isinstance(minimum_grade, str):
            raise ValueError("minimum_grade must be a string")
        return build_profile_ranking(
            self.catalog,
            profile,
            kinds=tuple(kinds),
            slot_ids=tuple(slots),
            limit_per_slot=limit,
            minimum_grade=minimum_grade,
        )

    def search(
        self,
        query: str,
        *,
        kind: str = "all",
        limit: int = 20,
    ) -> dict[str, Any]:
        needle = query.strip().casefold()
        if not needle:
            raise ValueError("search query must not be blank")
        limit = max(1, min(limit, 100))
        allowed = {"all", "skill", "affix", "item"}
        if kind not in allowed:
            raise ValueError(f"unknown search kind: {kind}")
        results: list[dict[str, object]] = []

        def add(candidate: dict[str, object], text: str) -> None:
            if len(results) < limit and needle in text.casefold():
                results.append(candidate)

        if kind in {"all", "skill"}:
            for skill in self.catalog.skills.skills:
                add(
                    {
                        "kind": "skill",
                        "id": skill.skill_id,
                        "name": skill.display_name,
                        "mastery_id": skill.mastery_id,
                    },
                    f"{skill.display_name} {skill.skill_id}",
                )
        if kind in {"all", "affix"}:
            for affix in self.catalog.affixes.affixes:
                add(
                    {
                        "kind": "affix",
                        "id": affix.affix_id,
                        "name": affix.display_name,
                        "affix_kind": affix.kind,
                    },
                    f"{affix.display_name} {affix.affix_id}",
                )
        if kind in {"all", "item"}:
            for item in self.catalog.items.all_items():
                add(
                    {
                        "kind": "item",
                        "id": item.item_id,
                        "name": item.display_name,
                        "item_type": item.family,
                    },
                    f"{item.display_name} {item.item_id}",
                )
        return {"query": query, "kind": kind, "results": results}


def openapi_document() -> dict[str, Any]:
    """Return a compact OpenAPI contract with no generated-SDK dependency."""

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Grim Gleaner Local Automation API",
            "version": "1.1.0",
            "description": "Local, deterministic profile and catalog operations.",
        },
        "servers": [{"url": "http://127.0.0.1:8765"}],
        "paths": {
            "/v1/health": {"get": {"summary": "Service and catalog status"}},
            "/v1/profile-schema": {
                "get": {"summary": "Current profile JSON Schema"}
            },
            "/v1/context": {
                "get": {"summary": "Profile discovery context"}
            },
            "/v1/catalog/search": {
                "get": {"summary": "Search skills, affixes, and items"}
            },
            "/v1/profiles/validate": {
                "post": {"summary": "Validate one profile"}
            },
            "/v1/profiles/diff": {
                "post": {"summary": "Compare two profiles semantically"}
            },
            "/v1/ranking": {
                "post": {
                    "summary": "Explainable gear ranking for a validated profile",
                    "description": (
                        "Ranks affixes, uniques, components, and augments per "
                        "slot. The request body takes a profile plus optional "
                        "kinds, slots, limit_per_slot, and minimum_grade. Each "
                        "result explains the grade with matched stat weights "
                        "and unmatched stat IDs."
                    ),
                }
            },
        },
    }


def _is_loopback_host(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def create_server(
    catalog: CatalogBundle,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    if not _is_loopback_host(host):
        raise ValueError(
            "automation API only permits loopback hosts until authentication "
            "is configured"
        )
    service = AutomationService(catalog)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            try:
                if parsed.path == "/v1/health":
                    payload = service.health()
                elif parsed.path == "/v1/profile-schema":
                    payload = profile_json_schema()
                elif parsed.path == "/v1/context":
                    payload = service.context(tuple(params.get("mastery", ())))
                elif parsed.path == "/v1/catalog/search":
                    payload = service.search(
                        params.get("q", [""])[0],
                        kind=params.get("kind", ["all"])[0],
                        limit=int(params.get("limit", ["20"])[0]),
                    )
                elif parsed.path == "/openapi.json":
                    payload = openapi_document()
                else:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
            except (TypeError, ValueError) as error:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._json_response(HTTPStatus.OK, payload)

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            try:
                payload = self._read_json()
                if self.path == "/v1/profiles/validate":
                    result = service.validate(payload)
                elif self.path == "/v1/profiles/diff":
                    result = service.diff(payload)
                elif self.path == "/v1/ranking":
                    result = service.ranking(payload)
                else:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            self._json_response(HTTPStatus.OK, result)

        def _read_json(self) -> object:
            raw_length = self.headers.get("Content-Length", "0")
            length = int(raw_length)
            if length < 1 or length > MAX_REQUEST_BYTES:
                raise ValueError("request body size is invalid")
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _json_response(self, status: HTTPStatus, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)
