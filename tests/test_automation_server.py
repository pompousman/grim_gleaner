from __future__ import annotations

from pathlib import Path

import pytest

from gd_affix_relevance.automation_server import (
    AutomationService,
    create_server,
    openapi_document,
)
from gd_affix_relevance.catalog import CatalogBundle
from gd_affix_relevance.domain import BuildProfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def service() -> AutomationService:
    catalog = CatalogBundle.load(PROJECT_ROOT / "artifacts" / "catalog")
    return AutomationService(catalog)


def _payload(profile: BuildProfile) -> dict[str, object]:
    return {"schema_version": 5, **profile.to_dict()}


def test_service_exposes_health_context_and_openapi(
    service: AutomationService,
) -> None:
    assert service.health()["status"] == "ok"
    context = service.context(("playerclass05",))
    assert context["selected_masteries"] == ["playerclass05"]
    assert "/v1/profiles/validate" in openapi_document()["paths"]


def test_service_validates_and_diffs_profiles(
    service: AutomationService,
) -> None:
    before = BuildProfile("Before")
    after = BuildProfile("After", {"health": 4})

    validation = service.validate(_payload(after))
    diff = service.diff({"before": _payload(before), "after": _payload(after)})

    assert validation["valid"] is True
    assert diff["summary"]["changes"] == 2
    assert {change["key"] for change in diff["changes"]} == {"name", "health"}


def test_server_rejects_non_loopback_bind(service: AutomationService) -> None:
    with pytest.raises(ValueError, match="loopback"):
        create_server(service.catalog, "0.0.0.0", 0)


def test_service_searches_catalog_with_bounded_results(
    service: AutomationService,
) -> None:
    result = service.search("Aether Ray", kind="skill", limit=5)

    assert 1 <= len(result["results"]) <= 5
    assert all(entry["kind"] == "skill" for entry in result["results"])
    assert any("Aether Ray" in entry["name"] for entry in result["results"])


def test_service_ranks_valid_profiles_with_explanations(
    service: AutomationService,
) -> None:
    profile = BuildProfile(
        "Lightning",
        {"flat_lightning_damage": 4, "lightning_damage_percent": 4},
    )
    payload = {
        "profile": _payload(profile),
        "kinds": ["affix"],
        "slots": ["ring"],
        "limit_per_slot": 2,
    }

    result = service.ranking(payload)

    assert result["protocol"] == "grim-gleaner-profile-ranking"
    assert result["request"]["slots"] == ["ring"]
    prefixes = result["slots"]["ring"]["prefixes"]
    assert prefixes
    assert all("weight" in stat for stat in prefixes[0]["matched_stats"])


def test_service_ranking_rejects_invalid_profiles(
    service: AutomationService,
) -> None:
    payload = {
        "profile": _payload(
            BuildProfile("Broken", {"nonexistent_stat": 4})
        ),
    }

    with pytest.raises(ValueError, match="failed validation"):
        service.ranking(payload)


def test_service_ranking_rejects_malformed_requests(
    service: AutomationService,
) -> None:
    with pytest.raises(ValueError, match="requires a profile"):
        service.ranking({"kinds": ["affix"]})
    with pytest.raises(ValueError, match="must be an object"):
        service.ranking(None)
    with pytest.raises(ValueError, match="list of strings"):
        service.ranking({"profile": _payload(BuildProfile("OK")), "kinds": 5})
    with pytest.raises(ValueError, match="list of strings"):
        service.ranking(
            {"profile": _payload(BuildProfile("OK")), "slots": "ring"}
        )
    with pytest.raises(ValueError, match="limit_per_slot"):
        service.ranking(
            {"profile": _payload(BuildProfile("OK")), "limit_per_slot": "many"}
        )
    with pytest.raises(ValueError, match="between 1 and"):
        service.ranking(
            {"profile": _payload(BuildProfile("OK")), "limit_per_slot": 99}
        )


def test_openapi_document_publishes_the_ranking_endpoint() -> None:
    document = openapi_document()

    assert "/v1/ranking" in document["paths"]
    assert document["info"]["version"] == "1.1.0"
