"""Tests for the explainable ranking export behind the automation API."""

from __future__ import annotations

from pathlib import Path

import pytest

from gd_affix_relevance.catalog import (
    AffixCatalog,
    AffixDefinition,
    AffixProperty,
    AffixVariantDefinition,
    CatalogBundle,
    CatalogManifest,
    ItemCatalog,
    ItemDefinition,
    ItemMonsterSource,
    ItemProperty,
    ItemSkillModifier,
    ItemVariantDefinition,
    ItemVendorSource,
    SkillCatalog,
    SkillDefinition,
    StringCatalog,
)
from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.ranking_export import (
    ALL_RANKING_SLOT_IDS,
    DEFAULT_LIMIT_PER_SLOT,
    RANKING_KINDS,
    build_profile_ranking,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> CatalogManifest:
    return CatalogManifest(
        schema_version=9,
        game_version="1.3.0.7",
        locale="en",
        sources=("base",),
        files=(),
        counts={},
        affix_scope="test",
        skill_scope="test",
        item_scope="test",
    )


def _skill(
    skill_id: str,
    name: str,
    *,
    mastery_id: str = "",
    mastery_name: str = "",
    is_mastery: bool = False,
) -> SkillDefinition:
    return SkillDefinition(
        skill_id=skill_id,
        source="base",
        category="test",
        name_tag=f"tag{name}",
        display_name=name,
        name_resolution="exact",
        description_tag="",
        mastery_id=mastery_id,
        mastery_name=mastery_name,
        mastery_level_required=0,
        max_level=12,
        is_mastery=is_mastery,
        skill_tier=1,
        tree_order=1,
    )


def _affix_variant(
    *property_ids: str,
    gear_slot: str = "Ring",
) -> AffixVariantDefinition:
    return AffixVariantDefinition(
        gear_slot=gear_slot,
        level_requirements=(50,),
        properties=tuple(
            AffixProperty(property_id, property_id, {})
            for property_id in property_ids
        ),
        stat_lines=tuple(property_id for property_id in property_ids),
        representative_source="base:records/items/example.dbr",
        source_record_count=1,
        stat_layout_count=1,
    )


def _affix(
    affix_id: str,
    name: str,
    kind: str,
    variant: AffixVariantDefinition,
) -> AffixDefinition:
    return AffixDefinition(
        affix_id=affix_id,
        localization_tag=f"tag{name}",
        display_name=name,
        kind=kind,
        variants=(variant,),
    )


def _item_variant(
    *,
    rarity: str = "legendary",
    item_class: str = "ArmorJewelry_Ring",
    properties: tuple[ItemProperty, ...] = (),
    stat_lines: tuple[str, ...] = (),
    level_requirement: int = 50,
    acquisition_source: str = "Random Drop",
    vendor_sources: tuple[ItemVendorSource, ...] = (),
    monster_sources: tuple[ItemMonsterSource, ...] = (),
    skill_modifiers: tuple[ItemSkillModifier, ...] = (),
    applicable_slots: tuple[str, ...] = ("Ring",),
) -> ItemVariantDefinition:
    return ItemVariantDefinition(
        source="base",
        record_path="records/items/gearhead/example.dbr",
        category="",
        rarity=rarity,
        item_class=item_class,
        gear_slot="Ring",
        item_level=50,
        level_requirement=level_requirement,
        applicable_slots=applicable_slots,
        set_reference="",
        set_name="",
        granted_skill_reference="",
        granted_skill_name="",
        effect_skill_reference="",
        effect_skill_name="",
        effect_properties=(),
        effect_stat_lines=(),
        completion_bonus_reference="",
        properties=properties,
        stat_lines=stat_lines,
        skill_modifiers=skill_modifiers,
        acquisition_source=acquisition_source,
        vendor_sources=vendor_sources,
        monster_sources=monster_sources,
    )


def _item(
    item_id: str,
    name: str,
    variant: ItemVariantDefinition,
) -> ItemDefinition:
    return ItemDefinition(
        item_id=item_id,
        family="gearhead",
        localization_tag=f"tag{name}",
        display_name=name,
        name_resolution="exact",
        description_tag="",
        description="",
        variants=(variant,),
    )


def _bundle(
    *,
    affixes: tuple[AffixDefinition, ...] = (),
    equipment: tuple[ItemDefinition, ...] = (),
    components: tuple[ItemDefinition, ...] = (),
    augments: tuple[ItemDefinition, ...] = (),
    skills: tuple[SkillDefinition, ...] = (),
) -> CatalogBundle:
    return CatalogBundle(
        manifest=_manifest(),
        strings=StringCatalog(locale="en", strings={}),
        skills=SkillCatalog(skills=skills),
        affixes=AffixCatalog(affixes=affixes),
        items=ItemCatalog(
            equipment=equipment,
            components=components,
            augments=augments,
            relics=(),
            runes=(),
            consumables=(),
        ),
    )


def _lightning_profile(**overrides: object) -> BuildProfile:
    weights = {
        "flat_lightning_damage": 4,
        "lightning_damage_percent": 4,
        "health": 2,
    }
    weights.update(overrides.pop("weights", {}))  # type: ignore[arg-type]
    return BuildProfile("Lightning", weights, **overrides)  # type: ignore[arg-type]


def test_ranking_explains_matched_and_unmatched_affix_stats() -> None:
    bundle = _bundle(
        affixes=(
            _affix(
                "prefix:tagStorm",
                "Storming",
                "prefix",
                _affix_variant(
                    "flat_lightning_damage",
                    "lightning_damage_percent",
                    "fire_resistance",
                ),
            ),
        ),
    )

    result = build_profile_ranking(
        bundle, _lightning_profile(), kinds=("affix",), slot_ids=("ring",)
    )

    assert result["protocol"] == "grim-gleaner-profile-ranking"
    assert result["protocol_version"] == 2
    assert result["request"] == {
        "kinds": ["affix"],
        "slots": ["ring"],
        "limit_per_slot": DEFAULT_LIMIT_PER_SLOT,
        "minimum_grade": "B",
    }
    assert result["grade_thresholds"]["S"] > result["grade_thresholds"]["A"]

    ring = result["slots"]["ring"]
    assert ring["label"] == "Ring"
    assert "uniques" not in ring

    assert len(ring["prefixes"]) == 1
    entry = ring["prefixes"][0]
    assert entry["kind"] == "affix"
    assert entry["affix_kind"] == "prefix"
    assert entry["name"] == "Storming"
    assert entry["marker"].startswith("[")
    assert entry["level_requirement"] == 50

    matched = {stat["id"]: stat for stat in entry["matched_stats"]}
    assert set(matched) == {
        "flat_lightning_damage",
        "lightning_damage_percent",
    }
    assert matched["flat_lightning_damage"]["weight"] == 4
    assert matched["flat_lightning_damage"]["label"] == (
        "Lightning Damage (Flat)"
    )

    unmatched = {stat["id"] for stat in entry["unmatched_stats"]}
    assert unmatched == {"fire_resistance"}

    assert entry["score"]["matched_count"] == 2
    assert entry["score"]["total_category_count"] == 3
    assert entry["stat_lines"] == [
        "flat_lightning_damage",
        "lightning_damage_percent",
        "fire_resistance",
    ]


def test_ranking_resolves_skill_and_mastery_stat_labels() -> None:
    bundle = _bundle(
        affixes=(
            _affix(
                "suffix:tagWitch",
                "of the Witch",
                "suffix",
                _affix_variant(
                    "skill_bonus:records/skills/playerclass05/primal_strike.dbr",
                    "mastery_bonus:playerclass05",
                ),
            ),
        ),
        skills=(
            _skill(
                "records/skills/playerclass05/primal_strike.dbr",
                "Primal Strike",
                mastery_id="playerclass05",
            ),
            _skill(
                "records/skills/playerclass05/mastery.dbr",
                "Shaman",
                mastery_id="playerclass05",
                mastery_name="Shaman",
                is_mastery=True,
            ),
        ),
    )
    profile = BuildProfile(
        "Shaman",
        {},
        masteries=("playerclass05", ""),
        skill_weights={
            "records/skills/playerclass05/primal_strike.dbr": 4
        },
    )

    result = build_profile_ranking(
        bundle, profile, kinds=("affix",), slot_ids=("ring",)
    )

    labels = {
        stat["id"]: stat["label"]
        for stat in result["slots"]["ring"]["suffixes"][0]["matched_stats"]
    }
    assert labels["skill_bonus:records/skills/playerclass05/primal_strike.dbr"] == (
        "Skill Bonus: Primal Strike"
    )
    assert labels["mastery_bonus:playerclass05"] == "Mastery Bonus: Shaman"


def test_ranking_includes_unique_items_with_sources() -> None:
    bundle = _bundle(
        equipment=(
            _item(
                "records/items/gearhead/storm_ring.dbr",
                "Storm Caller's Signet",
                _item_variant(
                    properties=(
                        ItemProperty(
                            "lightning_damage_percent",
                            "lightning_damage_percent",
                            {},
                        ),
                        ItemProperty("health", "health", {}),
                    ),
                    stat_lines=("+[x]% Lightning Damage", "+[x] Health"),
                    acquisition_source="Specific Monster Drop",
                    monster_sources=(
                        ItemMonsterSource(
                            "Bloodfeast", "tagBloodfeast", "Beast"
                        ),
                    ),
                ),
            ),
        ),
    )

    result = build_profile_ranking(
        bundle,
        _lightning_profile(),
        kinds=("unique",),
        slot_ids=("ring",),
        minimum_grade="D",
    )

    uniques = result["slots"]["ring"]["uniques"]
    assert len(uniques) == 1
    entry = uniques[0]
    assert entry["kind"] == "unique"
    assert entry["item_type"] == "legendary"
    assert entry["item_type_label"] == "Legendary"
    assert entry["name"] == "Storm Caller's Signet"
    assert entry["sources"] == {
        "acquisition": "Specific Monster Drop",
        "factions": [],
        "monsters": ["Bloodfeast"],
        "containers": [],
    }
    assert {stat["id"] for stat in entry["matched_stats"]} == {
        "lightning_damage_percent",
        "health",
    }


def test_ranking_includes_components_and_augments_with_factions() -> None:
    component = _item(
        "records/items/component/storm.dbr",
        "Seal of Storms",
        _item_variant(
            item_class="",
            applicable_slots=("Ring", "Amulet"),
            properties=(
                ItemProperty(
                    "flat_lightning_damage",
                    "flat_lightning_damage",
                    {},
                ),
            ),
            stat_lines=("[x]-[y] Lightning Damage",),
        ),
    )
    augment = _item(
        "records/items/augment/storm.dbr",
                "Storm Augment",
        _item_variant(
            item_class="",
            applicable_slots=("Ring",),
            properties=(
                ItemProperty(
                    "lightning_damage_percent",
                    "lightning_damage_percent",
                    {},
                ),
            ),
            stat_lines=("+[x]% Lightning Damage",),
            acquisition_source="Vendor",
            vendor_sources=(
                ItemVendorSource("factions/homestead", "Homestead", "Respected"),
            ),
        ),
    )
    bundle = _bundle(components=(component,), augments=(augment,))

    result = build_profile_ranking(
        bundle, _lightning_profile(), slot_ids=("ring",)
    )

    ring = result["slots"]["ring"]
    assert [entry["name"] for entry in ring["components"]] == [
        "Seal of Storms"
    ]
    assert ring["components"][0]["kind"] == "component"
    assert ring["components"][0]["addon_type_label"] == "Component"

    assert [entry["name"] for entry in ring["augments"]] == ["Storm Augment"]
    assert ring["augments"][0]["sources"]["factions"] == ["Homestead"]
    assert ring["augments"][0]["sources"]["acquisition"] == "Vendor"


def test_ranking_resistance_cap_mode_uses_cap_weights_for_addons() -> None:
    augment = _item(
        "records/items/augment/warding.dbr",
        "Warding Salve",
        _item_variant(
            item_class="",
            applicable_slots=("Ring",),
            properties=(
                ItemProperty("fire_resistance", "fire_resistance", {}),
            ),
            stat_lines=("+[x]% Fire Resistance",),
        ),
    )
    bundle = _bundle(augments=(augment,))
    profile = BuildProfile(
        "Cap",
        {"flat_lightning_damage": 4},
        resistance_cap_enabled=True,
        resistance_cap_weights={"fire_resistance": 2},
    )

    result = build_profile_ranking(
        bundle, profile, kinds=("augment",), slot_ids=("ring",)
    )

    assert result["profile"]["resistance_cap_mode"] is True
    entries = result["slots"]["ring"]["augments"]
    assert [entry["name"] for entry in entries] == ["Warding Salve"]
    assert entries[0]["matched_stats"][0]["id"] == "fire_resistance"
    # Resistance-cap mode doubles the effective weight, mirroring the UI.
    assert entries[0]["score"]["weighted_match"] == 4


def test_ranking_marks_selected_skill_modifiers_on_uniques() -> None:
    bundle = _bundle(
        equipment=(
            _item(
                "records/items/gearhead/mod_ring.dbr",
                "Modifier Ring",
                _item_variant(
                    properties=(
                        ItemProperty("health", "health", {}),
                    ),
                    skill_modifiers=(
                        ItemSkillModifier(
                            "records/skills/playerclass05/primal_strike.dbr",
                            "Primal Strike",
                            "records/skills/mods/storm.dbr",
                            (),
                            (),
                        ),
                    ),
                ),
            ),
        ),
        skills=(
            _skill(
                "records/skills/playerclass05/primal_strike.dbr",
                "Primal Strike",
                mastery_id="playerclass05",
            ),
        ),
    )
    profile = BuildProfile(
        "Shaman",
        {"health": 2},
        skill_weights={
            "records/skills/playerclass05/primal_strike.dbr": 4
        },
    )

    result = build_profile_ranking(
        bundle,
        profile,
        kinds=("unique",),
        slot_ids=("ring",),
        minimum_grade="D",
    )

    entry = result["slots"]["ring"]["uniques"][0]
    assert entry["has_selected_skill_modifier"] is True
    assert "!" in entry["marker"]
    modifier_ids = {
        stat["id"] for stat in entry["matched_stats"]
    }
    assert "skill_modifier:records/skills/playerclass05/primal_strike.dbr" in (
        modifier_ids
    )


def test_ranking_respects_limit_and_slot_aliases() -> None:
    affixes = tuple(
        _affix(
            f"prefix:tag{i}",
            f"Storming {i}",
            "prefix",
            _affix_variant(
                "flat_lightning_damage",
                "health",
                gear_slot=gear_slot,
            ),
        )
        for i, gear_slot in enumerate(("Ring",) * 6 + ("Waist",) * 6)
    )
    bundle = _bundle(affixes=affixes)

    result = build_profile_ranking(
        bundle,
        _lightning_profile(),
        kinds=("affix",),
        slot_ids=("belt", "Ring"),
        limit_per_slot=2,
    )

    assert result["request"]["slots"] == ["waist", "ring"]
    assert set(result["slots"]) == {"waist", "ring"}
    for slot in result["slots"].values():
        assert len(slot["prefixes"]) == 2


def test_ranking_rejects_unknown_kinds_slots_limits_and_grades() -> None:
    bundle = _bundle()
    profile = _lightning_profile()

    with pytest.raises(ValueError, match="unknown ranking kind"):
        build_profile_ranking(bundle, profile, kinds=("rune",))
    with pytest.raises(ValueError, match="unknown slot ID"):
        build_profile_ranking(bundle, profile, slot_ids=("holster",))
    with pytest.raises(ValueError, match="limit_per_slot"):
        build_profile_ranking(bundle, profile, limit_per_slot=0)
    with pytest.raises(ValueError, match="limit_per_slot"):
        build_profile_ranking(bundle, profile, limit_per_slot=21)
    with pytest.raises(ValueError, match="minimum grade"):
        build_profile_ranking(bundle, profile, minimum_grade="S9")


def test_ranking_defaults_cover_every_atomic_slot_and_kind() -> None:
    bundle = _bundle()
    result = build_profile_ranking(bundle, _lightning_profile())

    assert result["request"]["kinds"] == list(RANKING_KINDS)
    assert result["request"]["slots"] == list(ALL_RANKING_SLOT_IDS)
    assert result["request"]["limit_per_slot"] == DEFAULT_LIMIT_PER_SLOT


@pytest.fixture(scope="module")
def real_catalog() -> CatalogBundle:
    return CatalogBundle.load(PROJECT_ROOT / "artifacts" / "catalog")


def test_real_catalog_ranking_is_deterministic_and_explainable(
    real_catalog: CatalogBundle,
) -> None:
    profile = BuildProfile(
        "Lightning Integration",
        {
            "flat_lightning_damage": 4,
            "lightning_damage_percent": 4,
            "health": 2,
        },
    )

    first = build_profile_ranking(
        real_catalog,
        profile,
        kinds=("affix", "unique"),
        slot_ids=("ring",),
        limit_per_slot=3,
        minimum_grade="D",
    )
    second = build_profile_ranking(
        real_catalog,
        profile,
        kinds=("affix", "unique"),
        slot_ids=("ring",),
        limit_per_slot=3,
        minimum_grade="D",
    )

    assert first == second

    ring = first["slots"]["ring"]
    assert ring["prefixes"] and ring["suffixes"] and ring["uniques"]

    for entries in (ring["prefixes"], ring["suffixes"]):
        scores = [entry["score"]["effective_score"] for entry in entries]
        assert scores == sorted(scores, reverse=True)

    top_affix = ring["prefixes"][0]
    assert top_affix["matched_stats"]
    assert all("weight" in stat for stat in top_affix["matched_stats"])
    assert top_affix["grade"] in {"S++", "S+", "S", "A", "B", "C", "D"}

    top_unique = ring["uniques"][0]
    assert top_unique["sources"]["acquisition"]


def test_ranking_hints_match_the_real_engine_when_applied() -> None:
    bundle = _bundle(
        affixes=(
            _affix(
                "prefix:tagStorm",
                "Storming",
                "prefix",
                _affix_variant(
                    "flat_lightning_damage",
                    "health",
                ),
            ),
        ),
    )
    profile = BuildProfile("Lightning", {"flat_lightning_damage": 4})

    result = build_profile_ranking(
        bundle, profile, kinds=("affix",), slot_ids=("ring",)
    )
    entry = result["slots"]["ring"]["prefixes"][0]
    assert entry["grade"] == "C"
    assert entry["next_grade_hints"], "expected at least one counterfactual"

    hint = entry["next_grade_hints"][0]
    assert hint["stat_id"] == "health"
    assert 1 <= hint["weight"] <= 4
    assert hint["label"] == "Health (Flat)"

    # Applying the hint to the profile must reproduce the promised grade
    # through the normal ranking path.
    adjusted = BuildProfile(
        "Lightning",
        {"flat_lightning_damage": 4, "health": hint["weight"]},
    )
    re_ranked = build_profile_ranking(
        bundle, adjusted, kinds=("affix",), slot_ids=("ring",)
    )
    new_entry = next(
        candidate
        for candidate in re_ranked["slots"]["ring"]["prefixes"]
        if candidate["id"] == "prefix:tagStorm"
    )
    assert new_entry["grade"] == hint["resulting_grade"]
    assert new_entry["score"]["effective_score"] == pytest.approx(
        hint["resulting_score"]
    )


def test_ranking_hints_report_when_no_single_stat_reaches_next_grade() -> None:
    bundle = _bundle(
        affixes=(
            _affix(
                "prefix:tagDilute",
                "Diluted",
                "prefix",
                _affix_variant(
                    "flat_lightning_damage",
                    "lightning_damage_percent",
                    "health",
                    "fire_resistance",
                    "cold_resistance",
                ),
            ),
        ),
    )
    profile = BuildProfile(
        "Lightning",
        {"flat_lightning_damage": 4, "lightning_damage_percent": 4},
    )

    result = build_profile_ranking(
        bundle, profile, kinds=("affix",), slot_ids=("ring",)
    )

    entry = result["slots"]["ring"]["prefixes"][0]
    assert entry["grade"] == "B"
    assert entry["next_grade_hints"] == []


def test_ranking_hints_cover_selected_skill_weights() -> None:
    skill_id = "records/skills/playerclass05/primal_strike.dbr"
    bundle = _bundle(
        affixes=(
            _affix(
                "suffix:tagWitch",
                "of the Witch",
                "suffix",
                _affix_variant(
                    "skill_bonus:" + skill_id,
                    "health",
                ),
            ),
        ),
        skills=(
            _skill(skill_id, "Primal Strike", mastery_id="playerclass05"),
        ),
    )
    profile = BuildProfile("Shaman", {"health": 4})

    result = build_profile_ranking(
        bundle, profile, kinds=("affix",), slot_ids=("ring",)
    )
    entry = result["slots"]["ring"]["suffixes"][0]
    hints = entry["next_grade_hints"]
    skill_hint = next(
        (hint for hint in hints if hint["stat_id"] == "skill_bonus:" + skill_id),
        None,
    )
    assert skill_hint is not None
    assert skill_hint["label"] == "Skill Bonus: Primal Strike"

    adjusted = BuildProfile(
        "Shaman",
        {"health": 4},
        skill_weights={skill_id: skill_hint["weight"]},
    )
    re_ranked = build_profile_ranking(
        bundle, adjusted, kinds=("affix",), slot_ids=("ring",)
    )
    new_entry = next(
        candidate
        for candidate in re_ranked["slots"]["ring"]["suffixes"]
        if candidate["id"] == "suffix:tagWitch"
    )
    assert new_entry["grade"] == skill_hint["resulting_grade"]


def test_ranking_hints_in_cap_mode_adjust_resistance_cap_weights() -> None:
    augment = _item(
        "records/items/augment/warding.dbr",
        "Warding Salve",
        _item_variant(
            item_class="",
            applicable_slots=("Ring",),
            properties=(
                ItemProperty("flat_lightning_damage", "flat_lightning_damage", {}),
                ItemProperty("fire_resistance", "fire_resistance", {}),
            ),
            stat_lines=(
                "[x]-[y] Lightning Damage",
                "+[x]% Fire Resistance",
            ),
        ),
    )
    bundle = _bundle(augments=(augment,))
    profile = BuildProfile(
        "Cap",
        {"flat_lightning_damage": 4},
        resistance_cap_enabled=True,
        resistance_cap_weights={},
    )

    result = build_profile_ranking(
        bundle, profile, kinds=("augment",), slot_ids=("ring",)
    )
    entry = result["slots"]["ring"]["augments"][0]
    assert entry["next_grade_hints"]

    hint = entry["next_grade_hints"][0]
    assert hint["stat_id"] == "fire_resistance"

    # In cap mode the user action is a resistance-cap weight, and applying it
    # must reproduce the promised grade.
    adjusted = BuildProfile(
        "Cap",
        {"flat_lightning_damage": 4},
        resistance_cap_enabled=True,
        resistance_cap_weights={"fire_resistance": hint["weight"]},
    )
    re_ranked = build_profile_ranking(
        bundle, adjusted, kinds=("augment",), slot_ids=("ring",)
    )
    new_entry = re_ranked["slots"]["ring"]["augments"][0]
    assert new_entry["grade"] == hint["resulting_grade"]
    assert new_entry["score"]["effective_score"] == pytest.approx(
        hint["resulting_score"]
    )
