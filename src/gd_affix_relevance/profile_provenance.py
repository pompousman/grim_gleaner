"""Sidecar provenance for imported profiles, kept outside scoring data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from gd_affix_relevance.io_utils import atomic_write_text

PROVENANCE_SCHEMA_VERSION = 1


class ProfileProvenanceError(ValueError):
    """A provenance sidecar is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class ProvenanceVerification:
    valid: bool
    expected_sha256: str
    actual_sha256: str


@dataclass(frozen=True, slots=True)
class ProfileProvenance:
    source_kind: str
    source: str
    imported_at: str
    generator: str = ""
    source_url: str = ""
    catalog_game_version: str = ""
    catalog_schema_version: int = 0
    imported_profile_sha256: str = ""
    saved_profile_sha256: str = ""

    @classmethod
    def create(
        cls,
        *,
        source_kind: str,
        source: str,
        generator: str = "",
        source_url: str = "",
        catalog_game_version: str = "",
        catalog_schema_version: int = 0,
        imported_profile_text: str = "",
    ) -> ProfileProvenance:
        return cls(
            source_kind=source_kind,
            source=source,
            imported_at=datetime.now(UTC).isoformat(),
            generator=generator.strip(),
            source_url=source_url.strip(),
            catalog_game_version=catalog_game_version,
            catalog_schema_version=catalog_schema_version,
            imported_profile_sha256=_sha256_text(imported_profile_text),
        )


def provenance_path(profile_path: Path) -> Path:
    source = Path(profile_path)
    return source.with_name(f"{source.stem}.provenance.json")


def save_profile_provenance(
    profile_path: Path,
    provenance: ProfileProvenance,
) -> Path:
    """Write provenance beside a saved profile and bind it to saved bytes."""

    profile = Path(profile_path)
    saved_hash = hashlib.sha256(profile.read_bytes()).hexdigest()
    bound = replace(provenance, saved_profile_sha256=saved_hash)
    payload = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        **asdict(bound),
    }
    destination = provenance_path(profile)
    atomic_write_text(
        destination,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return destination


def load_profile_provenance(profile_path: Path) -> ProfileProvenance:
    """Load the sidecar associated with *profile_path*."""

    source = provenance_path(profile_path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileProvenanceError(
            f"Could not read profile provenance: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ProfileProvenanceError("Profile provenance must be a JSON object")
    if payload.pop("schema_version", None) != PROVENANCE_SCHEMA_VERSION:
        raise ProfileProvenanceError("Unsupported profile provenance schema")
    expected = set(ProfileProvenance.__dataclass_fields__)
    if set(payload) != expected:
        raise ProfileProvenanceError("Profile provenance fields do not match schema")
    try:
        return ProfileProvenance(**payload)
    except TypeError as error:
        raise ProfileProvenanceError(f"Invalid profile provenance: {error}") from error


def verify_profile_provenance(profile_path: Path) -> ProvenanceVerification:
    """Verify that a profile still matches its provenance sidecar hash."""

    profile = Path(profile_path)
    provenance = load_profile_provenance(profile)
    actual = hashlib.sha256(profile.read_bytes()).hexdigest()
    expected = provenance.saved_profile_sha256
    return ProvenanceVerification(
        valid=bool(expected) and expected == actual,
        expected_sha256=expected,
        actual_sha256=actual,
    )


def _sha256_text(text: str) -> str:
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
