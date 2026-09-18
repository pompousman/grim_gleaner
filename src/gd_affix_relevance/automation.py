"""Provider-neutral profile discovery and semantic validation.

The JSON returned by this module is deliberately plain data.  It can be used by
an LLM, a local script, a web application, or an editor extension without an
SDK or a vendor account.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import get_close_matches
from typing import Any

from gd_affix_relevance.catalog import CatalogBundle, SkillCatalog
from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.level_bands import LEVEL_BANDS
from gd_affix_relevance.profile_store import PROFILE_FILE_SCHEMA_VERSION
from gd_affix_relevance.stats.registry import (
    PROFILE_TABS,
    registered_stat_definitions,
    stat_is_scoreable,
)

AUTOMATION_PROTOCOL_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProfileDiagnostic:
    severity: str
    path: str
    message: str
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileValidationResult:
    valid: bool
    errors: tuple[ProfileDiagnostic, ...]
    warnings: tuple[ProfileDiagnostic, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [asdict(item) for item in self.errors],
            "warnings": [asdict(item) for item in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class ProfileChange:
    category: str
    key: str
    before: object
    after: object


@dataclass(frozen=True, slots=True)
class ProfileDiff:
    changes: tuple[ProfileChange, ...]

    @property
    def added(self) -> int:
        return sum(_change_is_empty(change, before=True) for change in self.changes)

    @property
    def removed(self) -> int:
        return sum(_change_is_empty(change, before=False) for change in self.changes)

    @property
    def modified(self) -> int:
        return len(self.changes) - self.added - self.removed

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "changes": len(self.changes),
                "added": self.added,
                "removed": self.removed,
                "modified": self.modified,
            },
            "changes": [asdict(change) for change in self.changes],
        }


def compare_profiles(before: BuildProfile, after: BuildProfile) -> ProfileDiff:
    """Return a stable semantic diff suitable for previews and code review."""

    changes: list[ProfileChange] = []

    def add_scalar(category: str, key: str, old: object, new: object) -> None:
        if old != new:
            changes.append(ProfileChange(category, key, old, new))

    add_scalar("profile", "name", before.name, after.name)
    add_scalar("profile", "level_band", before.level_band, after.level_band)
    for index in range(2):
        add_scalar(
            "mastery",
            str(index + 1),
            before.masteries[index],
            after.masteries[index],
        )
    add_scalar(
        "resistance_cap",
        "enabled",
        before.resistance_cap_enabled,
        after.resistance_cap_enabled,
    )
    for category, old_values, new_values in (
        ("stat", before.weights, after.weights),
        ("skill", before.skill_weights, after.skill_weights),
        (
            "resistance_cap",
            before.resistance_cap_weights,
            after.resistance_cap_weights,
        ),
    ):
        for key in sorted(set(old_values) | set(new_values)):
            add_scalar(
                category,
                key,
                old_values.get(key, 0),
                new_values.get(key, 0),
            )
    destinations = sorted(
        set(before.excluded_conversion_sources)
        | set(after.excluded_conversion_sources)
    )
    for destination in destinations:
        add_scalar(
            "conversion_exclusions",
            destination,
            tuple(sorted(before.excluded_conversion_sources.get(destination, ()))),
            tuple(sorted(after.excluded_conversion_sources.get(destination, ()))),
        )
    return ProfileDiff(tuple(changes))


def build_profile_context(
    catalog: CatalogBundle,
    *,
    mastery_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Describe the profile contract and valid IDs without assuming an AI vendor."""

    mastery_names = {
        skill.mastery_id: skill.mastery_name or skill.display_name
        for skill in catalog.skills.skills
        if skill.is_mastery and skill.mastery_id
    }
    skills_by_mastery: dict[str, list[dict[str, Any]]] = {
        mastery_id: [] for mastery_id in mastery_names
    }
    selectable_skills = tuple(
        skill
        for skill in catalog.skills.skills
        if (
            not skill.is_mastery
            and skill.mastery_id
            and skill.display_name
            and skill.skill_tier > 0
            and skill.tree_order > 0
        )
    )
    for skill in selectable_skills:
        skills_by_mastery.setdefault(skill.mastery_id, []).append(
            {
                "id": skill.skill_id,
                "name": skill.display_name,
                "parent_skill_id": skill.parent_skill_id,
                "tier": skill.skill_tier,
                "max_level": skill.max_level,
            }
        )

    unknown_masteries = sorted(set(mastery_ids) - set(skills_by_mastery))
    if unknown_masteries:
        raise ValueError(
            "unknown mastery ID(s): " + ", ".join(unknown_masteries)
        )

    selected = set(mastery_ids)
    masteries = []
    for mastery_id in sorted(skills_by_mastery, key=_mastery_sort_key):
        skills = sorted(
            skills_by_mastery[mastery_id],
            key=lambda value: (value["tier"], value["name"].casefold()),
        )
        entry: dict[str, Any] = {
            "id": mastery_id,
            "name": mastery_names.get(mastery_id, mastery_id),
            "skill_count": len(skills),
        }
        if mastery_id in selected:
            entry["skills"] = skills
        masteries.append(entry)

    tabs = [
        {
            "id": tab.tab_id,
            "label": tab.label,
            "packages": [
                {
                    "id": package.package_id,
                    "label": package.label,
                    "stats": [
                        {"id": definition.stat_id, "label": definition.label}
                        for definition in package.stats
                    ],
                }
                for package in tab.packages
            ],
        }
        for tab in PROFILE_TABS
    ]

    tab_stat_ids = {
        definition.stat_id
        for tab in PROFILE_TABS
        for package in tab.packages
        for definition in package.stats
    }
    global_stats = [
        {"id": definition.stat_id, "label": definition.label}
        for definition in registered_stat_definitions()
        if (
            definition.stat_id not in tab_stat_ids
            and stat_is_scoreable(definition.stat_id)
        )
    ]

    return {
        "protocol": "grim-gleaner-profile-context",
        "protocol_version": AUTOMATION_PROTOCOL_VERSION,
        "catalog": {
            "game_version": catalog.manifest.game_version,
            "schema_version": catalog.manifest.schema_version,
            "locale": catalog.manifest.locale,
        },
        "instructions": [
            "Return only one JSON object matching profile_schema.",
            "Use only stat, mastery, and skill IDs listed in this context.",
            "Weights are integers from 0 to 4; omit zero-weight entries.",
            "Choose exactly two distinct non-empty masteries for a dual-class build.",
            "Only select skills belonging to one of the chosen masteries.",
            "Treat user preferences as authoritative; explain assumptions "
            "outside the profile JSON if the calling interface permits it.",
        ],
        "weight_scale": [
            {"value": 0, "meaning": "ignored"},
            {"value": 1, "meaning": "incidental"},
            {"value": 2, "meaning": "useful"},
            {"value": 3, "meaning": "important"},
            {"value": 4, "meaning": "core"},
        ],
        "level_bands": [
            {
                "id": band.band_id,
                "minimum_level": band.minimum_level,
                "maximum_level": band.maximum_level,
            }
            for band in LEVEL_BANDS
        ],
        "stat_tabs": tabs,
        "global_stats": global_stats,
        "masteries": masteries,
        "selected_masteries": list(mastery_ids),
        "profile_schema": profile_json_schema(),
        "workflow": {
            "discover": "Generate this context without --mastery to list mastery IDs.",
            "focus": (
                "Generate it again with --mastery twice to include only those "
                "skill trees."
            ),
            "verify": "Run grim-gleaner validate-profile before importing the result.",
        },
    }


def profile_json_schema() -> dict[str, Any]:
    """Return the public interchange schema for a generated profile."""

    weight_map = {
        "type": "object",
        "additionalProperties": {"type": "integer", "minimum": 0, "maximum": 4},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://raw.githubusercontent.com/pompousman/grim_gleaner/"
            "main/schemas/profile.schema.json"
        ),
        "title": "Grim Gleaner build profile",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "name",
            "level_band",
            "masteries",
            "skill_weights",
            "weights",
            "resistance_cap_enabled",
            "resistance_cap_weights",
            "excluded_conversion_sources",
        ],
        "properties": {
            "schema_version": {"const": PROFILE_FILE_SCHEMA_VERSION},
            "name": {"type": "string", "minLength": 1},
            "level_band": {
                "type": "string",
                "enum": [band.band_id for band in LEVEL_BANDS],
            },
            "masteries": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 2,
            },
            "skill_weights": weight_map,
            "weights": weight_map,
            "resistance_cap_enabled": {"type": "boolean"},
            "resistance_cap_weights": weight_map,
            "excluded_conversion_sources": {
                "type": "object",
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"},
                    "uniqueItems": True,
                },
            },
        },
    }


def validate_profile_semantics(
    profile: BuildProfile,
    catalog: CatalogBundle | SkillCatalog,
) -> ProfileValidationResult:
    """Check IDs and cross-field relationships that JSON shape validation cannot."""

    errors: list[ProfileDiagnostic] = []
    warnings: list[ProfileDiagnostic] = []
    skills = catalog.skills if isinstance(catalog, CatalogBundle) else catalog
    if isinstance(skills, SkillCatalog):
        skill_definitions = skills.skills
    else:
        # ``CatalogBundle.skills`` is a SkillCatalog; this is defensive for
        # lightweight compatible catalog objects used by integrations.
        skill_definitions = tuple(skills)
    known_stats = {
        definition.stat_id
        for definition in registered_stat_definitions()
        if stat_is_scoreable(definition.stat_id)
    }
    known_skills = {
        skill.skill_id: skill
        for skill in skill_definitions
        if (
            not skill.is_mastery
            and skill.mastery_id
            and skill.display_name
            and skill.skill_tier > 0
            and skill.tree_order > 0
        )
    }
    known_masteries = {
        skill.mastery_id
        for skill in skill_definitions
        if skill.is_mastery and skill.mastery_id
    }

    for field_name, weights in (
        ("weights", profile.weights),
        ("resistance_cap_weights", profile.resistance_cap_weights),
    ):
        for stat_id in weights:
            if stat_id not in known_stats or not stat_is_scoreable(stat_id):
                errors.append(
                    _unknown_id_diagnostic(
                        f"$.{field_name}.{stat_id}", stat_id, known_stats, "stat"
                    )
                )

    chosen_masteries = {value for value in profile.masteries if value}
    for index, mastery_id in enumerate(profile.masteries):
        if mastery_id and mastery_id not in known_masteries:
            errors.append(
                _unknown_id_diagnostic(
                    f"$.masteries[{index}]",
                    mastery_id,
                    known_masteries,
                    "mastery",
                )
            )
    if len(chosen_masteries) < 2:
        warnings.append(
            ProfileDiagnostic(
                "warning",
                "$.masteries",
                "profile does not select two distinct masteries",
            )
        )

    for skill_id in profile.skill_weights:
        skill = known_skills.get(skill_id)
        if skill is None or skill.is_mastery:
            errors.append(
                _unknown_id_diagnostic(
                    f"$.skill_weights.{skill_id}",
                    skill_id,
                    set(known_skills),
                    "skill",
                )
            )
        elif skill.mastery_id not in chosen_masteries:
            errors.append(
                ProfileDiagnostic(
                    "error",
                    f"$.skill_weights.{skill_id}",
                    f"skill belongs to unselected mastery {skill.mastery_id!r}",
                    (skill.mastery_id,),
                )
            )

    return ProfileValidationResult(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _change_is_empty(change: ProfileChange, *, before: bool) -> bool:
    value = change.before if before else change.after
    if change.category in {"stat", "skill"}:
        return value == 0
    if change.category == "resistance_cap" and change.key != "enabled":
        return value == 0
    if change.category == "mastery":
        return value == ""
    if change.category == "conversion_exclusions":
        return value == ()
    return False


def _unknown_id_diagnostic(
    path: str,
    value: str,
    choices: set[str],
    kind: str,
) -> ProfileDiagnostic:
    return ProfileDiagnostic(
        "error",
        path,
        f"unknown or unsupported {kind} ID {value!r}",
        tuple(get_close_matches(value, choices, n=3, cutoff=0.55)),
    )


def _mastery_sort_key(mastery_id: str) -> tuple[int, str]:
    suffix = mastery_id.removeprefix("playerclass")
    return (int(suffix), mastery_id) if suffix.isdigit() else (999, mastery_id)
