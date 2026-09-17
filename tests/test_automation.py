from __future__ import annotations

import json
from pathlib import Path

import pytest

from gd_affix_relevance.automation import (
    build_profile_context,
    profile_json_schema,
    validate_profile_semantics,
)
from gd_affix_relevance.catalog import CatalogBundle
from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.profile_store import PROFILE_FILE_SCHEMA_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def catalog() -> CatalogBundle:
    return CatalogBundle.load(PROJECT_ROOT / "artifacts" / "catalog")


def test_profile_context_is_provider_neutral_and_focuses_skill_payload(
    catalog: CatalogBundle,
) -> None:
    context = build_profile_context(
        catalog,
        mastery_ids=("playerclass05", "playerclass08"),
    )

    assert context["protocol"] == "grim-gleaner-profile-context"
    assert context["profile_schema"]["properties"]["schema_version"] == {
        "const": PROFILE_FILE_SCHEMA_VERSION
    }
    selected = {
        mastery["id"]: mastery
        for mastery in context["masteries"]
        if "skills" in mastery
    }
    assert set(selected) == {"playerclass05", "playerclass08"}
    assert all(selected[mastery_id]["skills"] for mastery_id in selected)
    assert any(
        skill["max_level"] == 1
        for mastery in selected.values()
        for skill in mastery["skills"]
    )
    assert any(
        stat["id"] == "aether_damage_percent"
        for tab in context["stat_tabs"]
        for package in tab["packages"]
        for stat in package["stats"]
    )


def test_profile_context_rejects_unknown_mastery(catalog: CatalogBundle) -> None:
    with pytest.raises(ValueError, match="unknown mastery"):
        build_profile_context(catalog, mastery_ids=("not-a-class",))


def test_semantic_validation_reports_unknown_and_cross_mastery_ids(
    catalog: CatalogBundle,
) -> None:
    profile = BuildProfile(
        name="Generated candidate",
        masteries=("playerclass05", "playerclass08"),
        weights={"aether_damage_percnet": 4},
        skill_weights={"records/skills/playerclass03/doombolt1.dbr": 3},
    )

    result = validate_profile_semantics(profile, catalog)

    assert not result.valid
    assert any(
        diagnostic.path == "$.weights.aether_damage_percnet"
        and "aether_damage_percent" in diagnostic.suggestions
        for diagnostic in result.errors
    )
    assert any("unselected mastery" in item.message for item in result.errors)


def test_profile_schema_is_strict_and_versioned() -> None:
    schema = profile_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == 5
    assert schema["properties"]["weights"]["additionalProperties"]["maximum"] == 4
    checked_in = json.loads(
        (PROJECT_ROOT / "schemas" / "profile.schema.json").read_text(encoding="utf-8")
    )
    assert checked_in == schema
