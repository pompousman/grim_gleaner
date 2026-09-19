"""Tests for the atomic slot vocabulary and legacy label compatibility."""

from __future__ import annotations

from gd_affix_relevance.slots import (
    ARMOR_SLOTS,
    SLOT_AMULET,
    SLOT_CHEST,
    SLOT_HEAD,
    SLOT_HANDS,
    SLOT_LEGS,
    SLOT_MEDAL,
    SLOT_OFF_HAND,
    SLOT_RING,
    SLOT_SHIELD,
    SLOT_WAIST,
    SLOT_WEAPON_1H_CASTER,
    SLOT_WEAPON_1H_MELEE,
    SLOT_WEAPON_1H_RANGED,
    SLOT_WEAPON_2H_MELEE,
    SLOT_WEAPON_2H_RANGED,
    WEAPON_SLOTS,
    slot_ids_from_legacy_label,
)


def test_legacy_singular_and_plural_labels_resolve() -> None:
    assert slot_ids_from_legacy_label("Shield") == (SLOT_SHIELD,)
    assert slot_ids_from_legacy_label("Shields") == (SLOT_SHIELD,)
    assert slot_ids_from_legacy_label("Off-hand") == (SLOT_OFF_HAND,)
    assert slot_ids_from_legacy_label("Off-hands") == (SLOT_OFF_HAND,)
    assert slot_ids_from_legacy_label("Helm") == (SLOT_HEAD,)
    assert slot_ids_from_legacy_label("Belt") == (SLOT_WAIST,)


def test_legacy_weapon_group_labels_resolve() -> None:
    one_handed = (
        SLOT_WEAPON_1H_MELEE,
        SLOT_WEAPON_1H_CASTER,
        SLOT_WEAPON_1H_RANGED,
    )
    two_handed = (SLOT_WEAPON_2H_MELEE, SLOT_WEAPON_2H_RANGED)

    assert slot_ids_from_legacy_label("One-handed weapons") == one_handed
    assert slot_ids_from_legacy_label("All one-handed weapons") == one_handed
    assert slot_ids_from_legacy_label("Two-handed weapons") == two_handed
    assert slot_ids_from_legacy_label("All two-handed weapons") == two_handed
    assert slot_ids_from_legacy_label("All weapons") == WEAPON_SLOTS
    assert slot_ids_from_legacy_label("1H Melee") == (SLOT_WEAPON_1H_MELEE,)
    assert slot_ids_from_legacy_label("2H Ranged") == (SLOT_WEAPON_2H_RANGED,)


def test_legacy_compound_labels_resolve_every_part() -> None:
    # Regression: the old resolver split on "; " only and did not know the
    # component-style labels, so compound gear slots silently lost their
    # weapon parts.
    assert slot_ids_from_legacy_label("1H Melee; 1H Ranged") == (
        SLOT_WEAPON_1H_MELEE,
        SLOT_WEAPON_1H_RANGED,
    )
    assert slot_ids_from_legacy_label("1H Melee; 1H Caster; Medal; Chest") == (
        SLOT_WEAPON_1H_MELEE,
        SLOT_WEAPON_1H_CASTER,
        SLOT_MEDAL,
        SLOT_CHEST,
    )
    assert slot_ids_from_legacy_label("Helm; Pants; Gloves; Boots") == (
        SLOT_HEAD,
        SLOT_LEGS,
        SLOT_HANDS,
        "feet",
    )
    assert slot_ids_from_legacy_label("All armor; Shield") == (
        *ARMOR_SLOTS,
        SLOT_SHIELD,
    )


def test_legacy_labels_tolerate_spacing_and_case() -> None:
    assert slot_ids_from_legacy_label("1H Melee;1H Caster") == (
        SLOT_WEAPON_1H_MELEE,
        SLOT_WEAPON_1H_CASTER,
    )
    assert slot_ids_from_legacy_label(" ring ") == (SLOT_RING,)
    assert slot_ids_from_legacy_label("RING") == (SLOT_RING,)


def test_legacy_labels_deduplicate_and_ignore_unknown_parts() -> None:
    assert slot_ids_from_legacy_label("Ring; Ring; Amulet") == (
        SLOT_RING,
        SLOT_AMULET,
    )
    assert slot_ids_from_legacy_label("Ring; Unreleased Slot") == (SLOT_RING,)
    assert slot_ids_from_legacy_label("") == ()
