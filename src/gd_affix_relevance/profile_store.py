"""Versioned JSON persistence for user-created build profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.io_utils import atomic_write_text

PROFILE_FILE_SCHEMA_VERSION = 5
SUPPORTED_PROFILE_FILE_SCHEMA_VERSIONS = frozenset({1, 2, 3, 4, 5})
PROFILE_FILE_FIELDS = frozenset(
    {
        "schema_version",
        "name",
        "level_band",
        "masteries",
        "skill_weights",
        "weights",
        "resistance_cap_enabled",
        "resistance_cap_weights",
        "excluded_conversion_sources",
    }
)
CURRENT_PROFILE_REQUIRED_FIELDS = PROFILE_FILE_FIELDS


class ProfileFormatError(ValueError):
    """A profile file is not valid or uses an unsupported schema."""


def save_profile(profile: BuildProfile, path: Path) -> Path:
    """Atomically save *profile* and return the normalized destination path."""

    destination = _with_json_suffix(Path(path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": PROFILE_FILE_SCHEMA_VERSION,
        **profile.to_dict(),
    }
    atomic_write_text(
        destination,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return destination


def load_profile(path: Path) -> BuildProfile:
    """Load and validate a build profile from *path*."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise ProfileFormatError(f"Could not read profile: {error}") from error
    return load_profile_text(text)


def load_profile_text(text: str) -> BuildProfile:
    """Validate profile JSON supplied by a clipboard or integration."""

    try:
        payload: Any = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        raise ProfileFormatError(f"Could not read profile: {error}") from error
    return load_profile_payload(payload)


def load_profile_payload(payload: object) -> BuildProfile:
    """Validate an already-decoded profile object."""

    if not isinstance(payload, dict):
        raise ProfileFormatError("Profile file must contain a JSON object")

    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in SUPPORTED_PROFILE_FILE_SCHEMA_VERSIONS
    ):
        raise ProfileFormatError(
            f"Unsupported profile schema version: {schema_version!r}"
        )
    unknown_fields = set(payload) - PROFILE_FILE_FIELDS
    if unknown_fields:
        names = ", ".join(sorted(str(field) for field in unknown_fields))
        raise ProfileFormatError(f"Unknown profile field(s): {names}")
    try:
        profile = BuildProfile.from_dict(payload)
    except (TypeError, ValueError) as error:
        raise ProfileFormatError(f"Invalid profile data: {error}") from error
    if schema_version == PROFILE_FILE_SCHEMA_VERSION:
        missing_fields = CURRENT_PROFILE_REQUIRED_FIELDS - set(payload)
        if missing_fields:
            names = ", ".join(sorted(missing_fields))
            raise ProfileFormatError(f"Missing required profile field(s): {names}")
    return profile


def _with_json_suffix(path: Path) -> Path:
    if path.suffix:
        return path
    return path.with_suffix(".json")
