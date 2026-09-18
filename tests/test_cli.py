from __future__ import annotations

import json
from pathlib import Path

import pytest

from gd_affix_relevance.cli import build_parser, main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_every_cli_command_has_a_dispatch_handler() -> None:
    parser = build_parser()
    command_arguments = (
        ("inventory", "--data-root", "data", "--output-dir", "out"),
        (
            "sample",
            "--data-root",
            "data",
            "--localization-root",
            "text",
        ),
        ("rank", "--catalog-root", "catalog", "--profile-file", "profile.json"),
        (
            "rank-profile",
            "--catalog-root",
            "catalog",
            "--profile-file",
            "profile.json",
            "--kind",
            "affix",
            "--slot",
            "ring",
        ),
        (
            "compile-catalog",
            "--data-root",
            "data",
            "--localization-root",
            "text",
            "--output-dir",
            "out",
        ),
        (
            "generate-output",
            "--catalog-root",
            "catalog",
            "--profile-file",
            "profile.json",
            "--source-root",
            "text",
            "--output-dir",
            "out",
            "--locale",
            "ru",
        ),
        ("audit-items", "--data-root", "data"),
        (
            "audit-item-tags",
            "--data-root",
            "data",
            "--definition-source",
            "base",
            "--output-dir",
            "out",
        ),
        ("show-runtime-paths",),
        (
            "prepare-game-localization",
            "--game-folder",
            "game",
            "--locale",
            "ru",
        ),
        ("assemble-release",),
        ("profile-context", "--catalog-root", "catalog"),
        ("profile-schema",),
        (
            "validate-profile",
            "--catalog-root",
            "catalog",
            "--profile-file",
            "profile.json",
        ),
        (
            "diff-profiles",
            "--before",
            "before.json",
            "--after",
            "after.json",
        ),
        ("verify-profile-provenance", "--profile-file", "profile.json"),
        ("serve-automation", "--catalog-root", "catalog"),
    )

    for arguments in command_arguments:
        parsed = parser.parse_args(arguments)
        assert callable(parsed.handler)


@pytest.fixture(scope="module")
def _lightning_profile_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("rank-profile") / "lightning.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "name": "Lightning CLI",
                "level_band": "90+",
                "masteries": ("playerclass05", "playerclass08"),
                "skill_weights": {},
                "weights": {
                    "flat_lightning_damage": 4,
                    "lightning_damage_percent": 4,
                },
                "resistance_cap_enabled": False,
                "resistance_cap_weights": {},
                "excluded_conversion_sources": {},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_rank_profile_writes_explainable_ranking(
    tmp_path: Path,
    _lightning_profile_file: Path,
) -> None:
    output = tmp_path / "ranking.json"

    exit_code = main(
        (
            "rank-profile",
            "--catalog-root",
            str(PROJECT_ROOT / "artifacts" / "catalog"),
            "--profile-file",
            str(_lightning_profile_file),
            "--kind",
            "affix",
            "--slot",
            "ring",
            "--limit-per-slot",
            "2",
            "--output",
            str(output),
        )
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["protocol"] == "grim-gleaner-profile-ranking"
    assert payload["request"]["slots"] == ["ring"]
    ring = payload["slots"]["ring"]
    assert len(ring["prefixes"]) == 2
    assert ring["prefixes"][0]["matched_stats"]


def test_rank_profile_rejects_invalid_profiles(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = tmp_path / "broken.json"
    profile.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "name": "Broken",
                "level_band": "90+",
                "masteries": ("playerclass05", "playerclass08"),
                "skill_weights": {},
                "weights": {"nonexistent_stat": 4},
                "resistance_cap_enabled": False,
                "resistance_cap_weights": {},
                "excluded_conversion_sources": {},
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        (
            "rank-profile",
            "--catalog-root",
            str(PROJECT_ROOT / "artifacts" / "catalog"),
            "--profile-file",
            str(profile),
        )
    )

    assert exit_code == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary["valid"] is False
    assert "nonexistent_stat" in summary["errors"][0]["message"]
