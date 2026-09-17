from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from gd_affix_relevance.catalog import CatalogBundle
from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.profile_store import save_profile
from gd_affix_relevance.ui.profile_automation import ProfileAutomationWidget
from gd_affix_relevance.ui.profile_editor import ProfileEditor


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def catalog() -> CatalogBundle:
    return CatalogBundle.load(PROJECT_ROOT / "artifacts" / "catalog")


def test_ui_exports_schema_and_focused_context(
    tmp_path: Path,
    catalog: CatalogBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _application()
    profile = BuildProfile(
        masteries=("playerclass05", "playerclass08"),
    )
    widget = ProfileAutomationWidget(profile, catalog, tmp_path)
    destinations = iter((tmp_path / "schema.json", tmp_path / "context.json"))
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(next(destinations)), ""),
    )

    widget.schema_button.click()
    widget.context_button.click()

    schema = json.loads((tmp_path / "schema.json").read_text(encoding="utf-8"))
    context = json.loads((tmp_path / "context.json").read_text(encoding="utf-8"))
    assert schema["title"] == "Grim Gleaner build profile"
    assert context["selected_masteries"] == ["playerclass05", "playerclass08"]
    assert {
        mastery["id"]
        for mastery in context["masteries"]
        if "skills" in mastery
    } == {"playerclass05", "playerclass08"}


def test_ui_blocks_invalid_generated_profile(
    tmp_path: Path,
    catalog: CatalogBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _application()
    candidate = BuildProfile(
        name="Bad generator output",
        masteries=("playerclass05", "playerclass08"),
        weights={"aether_damage_percnet": 4},
    )
    path = save_profile(candidate, tmp_path / "bad.json")
    widget = ProfileAutomationWidget(BuildProfile(), catalog, tmp_path)
    imported: list[Path] = []
    widget.import_requested.connect(imported.append)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(path), ""),
    )

    widget._choose_candidate(import_after_validation=True)

    assert "INVALID" in widget.diagnostics.toPlainText()
    assert "aether_damage_percent" in widget.diagnostics.toPlainText()
    assert imported == []


def test_ui_confirms_valid_profile_before_import(
    tmp_path: Path,
    catalog: CatalogBundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _application()
    candidate = BuildProfile(
        name="Valid generated profile",
        masteries=("playerclass05", "playerclass08"),
        weights={"aether_damage_percent": 4},
        skill_weights={"records/skills/playerclass05/aetherray1.dbr": 4},
    )
    path = save_profile(candidate, tmp_path / "valid.json")
    widget = ProfileAutomationWidget(BuildProfile(), catalog, tmp_path)
    imported: list[Path] = []
    widget.import_requested.connect(imported.append)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(path), ""),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    widget._choose_candidate(import_after_validation=True)

    assert imported == [path]
    assert "VALID" in widget.diagnostics.toPlainText()


def test_editor_rejects_semantically_invalid_profile(
    tmp_path: Path,
    catalog: CatalogBundle,
) -> None:
    _application()
    invalid = BuildProfile(
        masteries=("playerclass05", "playerclass08"),
        weights={"not_a_real_stat": 4},
    )
    path = save_profile(invalid, tmp_path / "invalid.json")
    editor = ProfileEditor(
        BuildProfile(),
        skills=catalog.skills,
        catalog_bundle=catalog,
        profiles_root=tmp_path,
    )

    with pytest.raises(ValueError, match="semantic validation"):
        editor.load_from_path(path)


def test_editor_imports_generated_profile_as_unsaved_draft(
    tmp_path: Path,
    catalog: CatalogBundle,
) -> None:
    _application()
    candidate = BuildProfile(
        name="Generated draft",
        masteries=("playerclass05", "playerclass08"),
        weights={"aether_damage_percent": 4},
    )
    path = save_profile(candidate, tmp_path / "generated.json")
    editor = ProfileEditor(
        BuildProfile(),
        skills=catalog.skills,
        catalog_bundle=catalog,
        profiles_root=tmp_path,
    )

    editor._import_generated_profile(path)

    assert editor.profile.name == "Generated draft"
    assert editor.current_profile_path is None
    assert editor.is_dirty
    assert "Imported draft" in editor.file_status.text()
