"""Explainable, machine-readable gear rankings for a validated build profile.

The JSON produced here is deliberately plain data, mirroring
``automation.py``: an agent, script, editor extension, or web client can
consume it without an SDK or a vendor account.  Every ranked entry carries
the signals behind its grade so integrations can explain *why* something
ranked where it did instead of trusting an opaque score.
"""

from __future__ import annotations

from typing import Any

from gd_affix_relevance.catalog import CatalogBundle
from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.scoring.catalog_scorer import (
    GRADE_THRESHOLDS,
    RankedAffixVariant,
    minimum_score_for_grade,
    profile_weight_for_semantic_id,
    rank_affixes_for_slot,
)
from gd_affix_relevance.scoring.item_scorer import (
    ADDON_AUGMENT,
    ADDON_COMPONENT,
    ADDON_TYPE_LABELS,
    UNIQUE_TYPE_LABELS,
    RankedAddonVariant,
    RankedItemVariant,
    rank_addons_for_slot,
    rank_unique_items_for_slot,
)
from gd_affix_relevance.slots import (
    SLOT_GROUPS,
    SLOT_LABELS,
    slot_ids_from_legacy_label,
)
from gd_affix_relevance.stats.registry import stat_definition

RANKING_PROTOCOL_VERSION = 1
RANKING_PROTOCOL_NAME = "grim-gleaner-profile-ranking"

RANKING_KINDS = ("affix", "unique", "component", "augment")
MAX_LIMIT_PER_SLOT = 20
DEFAULT_LIMIT_PER_SLOT = 5
DEFAULT_MINIMUM_GRADE = "B"

ALL_RANKING_SLOT_IDS: tuple[str, ...] = tuple(
    slot_id for _, group in SLOT_GROUPS for slot_id in group
)

# Friendly aliases accepted in ranking requests.  Canonical IDs come from
# ``ALL_RANKING_SLOT_IDS``; these cover common shorthand and the legacy
# gear-slot labels used by hand-built catalogs.
_SLOT_ALIASES = {
    "belt": "waist",
    "helm": "head",
    "pants": "legs",
    "gloves": "hands",
    "boots": "feet",
    "shoulder": "shoulders",
    "weapon": "weapon_1h_melee",
    "1h": "weapon_1h_melee",
    "2h": "weapon_2h_melee",
    "melee": "weapon_1h_melee",
    "caster": "weapon_1h_caster",
    "ranged": "weapon_1h_ranged",
    "offhand": "off_hand",
    "jewelry": "ring",
}


class _StatLabeler:
    """Resolve semantic stat IDs to human labels without repeated lookups."""

    def __init__(self, catalog: CatalogBundle) -> None:
        self._skills_by_id = catalog.skills.by_id()
        self._masteries = {
            skill.mastery_id: skill.mastery_name or skill.display_name
            for skill in catalog.skills.skills
            if skill.is_mastery and skill.mastery_id
        }

    def label(self, stat_id: str) -> str:
        definition = stat_definition(stat_id)
        if definition is not None:
            return definition.label
        for prefix, base in (
            ("skill_bonus:", "Skill Bonus"),
            ("skill_modifier:", "Skill Modifier"),
        ):
            if stat_id.startswith(prefix):
                skill = self._skills_by_id.get(stat_id[len(prefix) :])
                if skill is not None:
                    return f"{base}: {skill.display_name}"
        if stat_id.startswith("mastery_bonus:"):
            mastery_name = self._masteries.get(
                stat_id[len("mastery_bonus:") :]
            )
            if mastery_name is not None:
                return f"Mastery Bonus: {mastery_name}"
        return stat_id.replace("_", " ").title()


def _stat_entries(
    labeler: _StatLabeler,
    stat_ids: tuple[str, ...],
    *,
    profile: BuildProfile | None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for stat_id in stat_ids:
        entry: dict[str, Any] = {
            "id": stat_id,
            "label": labeler.label(stat_id),
        }
        if profile is not None:
            entry["weight"] = profile_weight_for_semantic_id(profile, stat_id)
        entries.append(entry)
    return entries


def _score_block(score: Any) -> dict[str, Any]:
    return {
        "grade": score.grade,
        "effective_score": round(score.effective_score, 4),
        "relevance_points": round(score.relevance_points, 4),
        "weighted_match": score.weighted_match,
        "matched_count": score.matched_count,
        "total_category_count": score.total_category_count,
        "coverage_ratio": round(score.coverage_ratio, 4),
    }


def _unmatched_stat_ids(
    semantic_stat_ids: tuple[str, ...],
    matched_stat_ids: tuple[str, ...],
) -> tuple[str, ...]:
    matched = set(matched_stat_ids)
    return tuple(
        stat_id for stat_id in semantic_stat_ids if stat_id not in matched
    )


def _explanation_fields(
    *,
    labeler: _StatLabeler,
    profile: BuildProfile,
    semantic_stat_ids: tuple[str, ...],
    score: Any,
) -> dict[str, Any]:
    return {
        "score": _score_block(score),
        "matched_stats": _stat_entries(
            labeler, score.matched_stat_ids, profile=profile
        ),
        "unmatched_stats": _stat_entries(
            labeler,
            _unmatched_stat_ids(semantic_stat_ids, score.matched_stat_ids),
            profile=None,
        ),
    }


def _affix_entry(
    match: RankedAffixVariant,
    *,
    labeler: _StatLabeler,
    profile: BuildProfile,
) -> dict[str, Any]:
    return {
        "kind": "affix",
        "affix_kind": match.affix.kind,
        "id": match.affix.affix_id,
        "name": match.affix.display_name,
        "marker": match.marker,
        "grade": match.score.grade,
        "level_requirement": max(
            match.variant.level_requirements, default=0
        ),
        "has_level_variations": match.has_level_variations,
        **_explanation_fields(
            labeler=labeler,
            profile=profile,
            semantic_stat_ids=match.semantic_stat_ids,
            score=match.score,
        ),
        "stat_lines": list(match.variant.stat_lines),
    }


def _source_block(variant: Any) -> dict[str, Any]:
    return {
        "acquisition": variant.acquisition_source,
        "factions": [
            source.faction_name or source.faction_source
            for source in variant.vendor_sources
            if source.faction_name or source.faction_source
        ],
        "monsters": [source.name for source in variant.monster_sources],
        "containers": [source.name for source in variant.container_sources],
    }


def _unique_entry(
    match: RankedItemVariant,
    *,
    labeler: _StatLabeler,
    profile: BuildProfile,
) -> dict[str, Any]:
    return {
        "kind": "unique",
        "item_type": match.item_type,
        "item_type_label": UNIQUE_TYPE_LABELS.get(
            match.item_type, match.item_type
        ),
        "id": match.item.item_id,
        "name": match.item.display_name,
        "marker": match.marker,
        "grade": match.score.grade,
        "level_requirement": match.variant.level_requirement,
        "item_level": match.variant.item_level,
        "has_selected_skill_modifier": match.has_selected_skill_modifier,
        "granted_skill": match.variant.granted_skill_name
        or match.variant.granted_skill_reference,
        **_explanation_fields(
            labeler=labeler,
            profile=profile,
            semantic_stat_ids=match.semantic_stat_ids,
            score=match.score,
        ),
        "stat_lines": list(match.variant.stat_lines),
        "sources": _source_block(match.variant),
    }


def _addon_entry(
    match: RankedAddonVariant,
    *,
    labeler: _StatLabeler,
    profile: BuildProfile,
) -> dict[str, Any]:
    return {
        "kind": match.addon_type,
        "addon_type_label": ADDON_TYPE_LABELS[match.addon_type],
        "id": match.item.item_id,
        "name": match.item.display_name,
        "marker": match.marker,
        "grade": match.score.grade,
        "level_requirement": match.variant.level_requirement,
        "has_selected_skill_modifier": match.has_selected_skill_modifier,
        "granted_skill": match.variant.granted_skill_name
        or match.variant.granted_skill_reference,
        **_explanation_fields(
            labeler=labeler,
            profile=profile,
            semantic_stat_ids=match.semantic_stat_ids,
            score=match.score,
        ),
        "stat_lines": list(match.variant.stat_lines),
        "sources": _source_block(match.variant),
    }


def _normalize_kinds(kinds: tuple[str, ...]) -> tuple[str, ...]:
    if not kinds:
        return RANKING_KINDS
    unknown = [kind for kind in kinds if kind not in RANKING_KINDS]
    if unknown:
        raise ValueError(
            "unknown ranking kind(s): "
            + ", ".join(unknown)
            + f"; expected any of {', '.join(RANKING_KINDS)}"
        )
    return tuple(dict.fromkeys(kinds))


def _resolve_slot_id(candidate: str) -> tuple[str, ...]:
    """Resolve one request slot name to canonical atomic slot IDs."""

    known = set(ALL_RANKING_SLOT_IDS)
    if candidate in known:
        return (candidate,)
    lowered = candidate.casefold()
    if lowered in known:
        return (lowered,)
    alias = _SLOT_ALIASES.get(lowered)
    if alias is not None:
        return (alias,)
    legacy = slot_ids_from_legacy_label(candidate)
    if legacy and any(slot_id in known for slot_id in legacy):
        return tuple(slot_id for slot_id in legacy if slot_id in known)
    return ()


def _normalize_slots(slot_ids: tuple[str, ...]) -> tuple[str, ...]:
    if not slot_ids:
        return ALL_RANKING_SLOT_IDS
    resolved: list[str] = []
    unknown: list[str] = []
    for slot_id in slot_ids:
        matches = _resolve_slot_id(slot_id)
        if matches:
            resolved.extend(matches)
        else:
            unknown.append(slot_id)
    if unknown:
        raise ValueError(
            "unknown slot ID(s): "
            + ", ".join(unknown)
            + f"; expected any of {', '.join(ALL_RANKING_SLOT_IDS)}"
        )
    return tuple(dict.fromkeys(resolved))


def build_profile_ranking(
    catalog: CatalogBundle,
    profile: BuildProfile,
    *,
    kinds: tuple[str, ...] = RANKING_KINDS,
    slot_ids: tuple[str, ...] = (),
    limit_per_slot: int = DEFAULT_LIMIT_PER_SLOT,
    minimum_grade: str = DEFAULT_MINIMUM_GRADE,
) -> dict[str, Any]:
    """Rank the compiled catalog for *profile* with explainable results.

    The response mirrors what the Gear Grades screen shows: per atomic slot,
    the top affix prefixes/suffixes, unique items, and add-ons, each with the
    matched stat weights and unmatched stat IDs that produced the grade.
    """

    kinds = _normalize_kinds(kinds)
    slots = _normalize_slots(slot_ids)
    if not 1 <= limit_per_slot <= MAX_LIMIT_PER_SLOT:
        raise ValueError(
            f"limit_per_slot must be between 1 and {MAX_LIMIT_PER_SLOT}"
        )
    minimum_score_for_grade(minimum_grade)

    labeler = _StatLabeler(catalog)
    resistance_cap_weights = (
        profile.resistance_cap_weights
        if profile.resistance_cap_enabled
        else None
    )

    slot_results: dict[str, Any] = {}
    for slot_id in slots:
        entry: dict[str, Any] = {
            "label": SLOT_LABELS.get(slot_id, slot_id),
        }
        if "affix" in kinds:
            entry["prefixes"] = [
                _affix_entry(match, labeler=labeler, profile=profile)
                for match in rank_affixes_for_slot(
                    catalog.affixes,
                    profile,
                    slot_id=slot_id,
                    kind="prefix",
                    limit=limit_per_slot,
                )
            ]
            entry["suffixes"] = [
                _affix_entry(match, labeler=labeler, profile=profile)
                for match in rank_affixes_for_slot(
                    catalog.affixes,
                    profile,
                    slot_id=slot_id,
                    kind="suffix",
                    limit=limit_per_slot,
                )
            ]
        if "unique" in kinds:
            entry["uniques"] = [
                _unique_entry(match, labeler=labeler, profile=profile)
                for match in rank_unique_items_for_slot(
                    catalog.items,
                    profile,
                    slot_id=slot_id,
                    minimum_grade=minimum_grade,
                )[:limit_per_slot]
            ]
        if "component" in kinds:
            entry["components"] = [
                _addon_entry(match, labeler=labeler, profile=profile)
                for match in rank_addons_for_slot(
                    catalog.items,
                    profile,
                    slot_id=slot_id,
                    addon_type=ADDON_COMPONENT,
                    limit=limit_per_slot,
                    resistance_cap_weights=resistance_cap_weights,
                )
            ]
        if "augment" in kinds:
            entry["augments"] = [
                _addon_entry(match, labeler=labeler, profile=profile)
                for match in rank_addons_for_slot(
                    catalog.items,
                    profile,
                    slot_id=slot_id,
                    addon_type=ADDON_AUGMENT,
                    limit=limit_per_slot,
                    resistance_cap_weights=resistance_cap_weights,
                )
            ]
        slot_results[slot_id] = entry

    return {
        "protocol": RANKING_PROTOCOL_NAME,
        "protocol_version": RANKING_PROTOCOL_VERSION,
        "catalog": {
            "game_version": catalog.manifest.game_version,
            "schema_version": catalog.manifest.schema_version,
            "locale": catalog.manifest.locale,
        },
        "profile": {
            "name": profile.name,
            "level_band": profile.level_band,
            "masteries": list(profile.masteries),
            "selected_skill_count": len(profile.skill_weights),
            "resistance_cap_mode": profile.resistance_cap_enabled,
        },
        "request": {
            "kinds": list(kinds),
            "slots": list(slots),
            "limit_per_slot": limit_per_slot,
            "minimum_grade": minimum_grade,
        },
        "grade_thresholds": dict(
            sorted(GRADE_THRESHOLDS.items(), key=lambda item: -item[1])
        ),
        "slots": slot_results,
    }
