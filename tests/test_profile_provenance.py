from __future__ import annotations

import hashlib
import json
from pathlib import Path

from gd_affix_relevance.cli import main
from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.profile_provenance import (
    ProfileProvenance,
    provenance_path,
    save_profile_provenance,
    verify_profile_provenance,
)
from gd_affix_relevance.profile_store import save_profile


def test_provenance_is_a_hash_bound_sidecar(tmp_path: Path) -> None:
    imported_text = '{"source": "assistant"}'
    provenance = ProfileProvenance.create(
        source_kind="clipboard",
        source="system clipboard",
        generator="Local Model",
        source_url="https://example.invalid/build",
        catalog_game_version="1.3.0.7",
        catalog_schema_version=9,
        imported_profile_text=imported_text,
    )
    profile_path = save_profile(BuildProfile("Imported"), tmp_path / "build.json")

    destination = save_profile_provenance(profile_path, provenance)
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert destination == provenance_path(profile_path)
    assert destination.name == "build.provenance.json"
    assert payload["schema_version"] == 1
    assert payload["generator"] == "Local Model"
    assert payload["imported_profile_sha256"] == hashlib.sha256(
        imported_text.encode("utf-8")
    ).hexdigest()
    assert payload["saved_profile_sha256"] == hashlib.sha256(
        profile_path.read_bytes()
    ).hexdigest()
    assert verify_profile_provenance(profile_path).valid

    profile_path.write_text("tampered", encoding="utf-8")
    verification = verify_profile_provenance(profile_path)
    assert not verification.valid
    assert verification.expected_sha256 != verification.actual_sha256


def test_provenance_verification_is_available_from_cli(
    tmp_path: Path,
    capsys,
) -> None:
    profile_path = save_profile(BuildProfile("CLI"), tmp_path / "cli.json")
    provenance = ProfileProvenance.create(
        source_kind="file",
        source="candidate.json",
    )
    save_profile_provenance(profile_path, provenance)

    exit_code = main(
        ["verify-profile-provenance", "--profile-file", str(profile_path)]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["valid"] is True
