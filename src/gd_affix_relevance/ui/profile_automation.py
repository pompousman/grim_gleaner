"""Provider-neutral profile exchange controls for the desktop UI."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gd_affix_relevance.automation import (
    ProfileValidationResult,
    build_profile_context,
    profile_json_schema,
    validate_profile_semantics,
)
from gd_affix_relevance.catalog import CatalogBundle
from gd_affix_relevance.domain import BuildProfile
from gd_affix_relevance.io_utils import atomic_write_text
from gd_affix_relevance.profile_store import load_profile
from gd_affix_relevance.ui.i18n import t


class ProfileAutomationWidget(QWidget):
    """Export the public contract and safely inspect generated profiles."""

    import_requested = Signal(object)

    def __init__(
        self,
        profile: BuildProfile,
        catalog: CatalogBundle | None,
        output_root: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile = profile
        self.catalog = catalog
        self.output_root = Path(output_root)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(12)

        title = QLabel(t("automation.title"), self)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        explanation = QLabel(t("automation.explanation"), self)
        explanation.setObjectName("pageHint")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        privacy = QLabel(t("automation.privacy"), self)
        privacy.setObjectName("automationPrivacy")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)

        export_frame = QFrame(self)
        export_frame.setObjectName("automationCard")
        export_layout = QVBoxLayout(export_frame)
        export_heading = QLabel(t("automation.export_title"), export_frame)
        export_heading.setObjectName("fieldLabel")
        export_layout.addWidget(export_heading)
        self.selection_summary = QLabel(export_frame)
        self.selection_summary.setWordWrap(True)
        export_layout.addWidget(self.selection_summary)

        export_buttons = QHBoxLayout()
        self.schema_button = QPushButton(
            t("automation.save_schema"), export_frame
        )
        self.schema_button.setObjectName("profileAction")
        self.schema_button.clicked.connect(self._save_schema)
        export_buttons.addWidget(self.schema_button)
        self.context_button = QPushButton(
            t("automation.save_context"), export_frame
        )
        self.context_button.setObjectName("primaryAction")
        self.context_button.clicked.connect(self._save_context)
        export_buttons.addWidget(self.context_button)
        self.copy_button = QPushButton(
            t("automation.copy_context"), export_frame
        )
        self.copy_button.setObjectName("profileAction")
        self.copy_button.clicked.connect(self._copy_context)
        export_buttons.addWidget(self.copy_button)
        export_buttons.addStretch()
        export_layout.addLayout(export_buttons)
        layout.addWidget(export_frame)

        import_frame = QFrame(self)
        import_frame.setObjectName("automationCard")
        import_layout = QVBoxLayout(import_frame)
        import_heading = QLabel(t("automation.import_title"), import_frame)
        import_heading.setObjectName("fieldLabel")
        import_layout.addWidget(import_heading)
        import_hint = QLabel(t("automation.import_hint"), import_frame)
        import_hint.setWordWrap(True)
        import_layout.addWidget(import_hint)
        import_buttons = QHBoxLayout()
        self.validate_button = QPushButton(
            t("automation.validate_button"), import_frame
        )
        self.validate_button.setObjectName("profileAction")
        self.validate_button.clicked.connect(
            lambda: self._choose_candidate(import_after_validation=False)
        )
        import_buttons.addWidget(self.validate_button)
        self.import_button = QPushButton(
            t("automation.import_button"), import_frame
        )
        self.import_button.setObjectName("primaryAction")
        self.import_button.clicked.connect(
            lambda: self._choose_candidate(import_after_validation=True)
        )
        import_buttons.addWidget(self.import_button)
        import_buttons.addStretch()
        import_layout.addLayout(import_buttons)
        self.diagnostics = QPlainTextEdit(import_frame)
        self.diagnostics.setObjectName("automationDiagnostics")
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlaceholderText(t("automation.diagnostics_empty"))
        self.diagnostics.setMaximumHeight(170)
        import_layout.addWidget(self.diagnostics)
        layout.addWidget(import_frame)
        layout.addStretch()

        catalog_available = self.catalog is not None
        self.context_button.setEnabled(catalog_available)
        self.copy_button.setEnabled(catalog_available)
        self.validate_button.setEnabled(catalog_available)
        self.import_button.setEnabled(catalog_available)
        if not catalog_available:
            self.diagnostics.setPlainText(t("automation.catalog_unavailable"))
        self.refresh_from_profile()

    def refresh_from_profile(self) -> None:
        selected = tuple(value for value in self.profile.masteries if value)
        if selected:
            selection = ", ".join(selected)
            self.selection_summary.setText(
                t("automation.selection", masteries=selection)
            )
        else:
            self.selection_summary.setText(t("automation.no_selection"))

    def _context_payload(self) -> dict[str, object]:
        if self.catalog is None:
            raise ValueError(t("automation.catalog_unavailable"))
        mastery_ids = tuple(value for value in self.profile.masteries if value)
        return build_profile_context(self.catalog, mastery_ids=mastery_ids)

    def _save_schema(self) -> None:
        self._save_json_payload(
            profile_json_schema(),
            "profile.schema.json",
            t("automation.schema_dialog_title"),
        )

    def _save_context(self) -> None:
        try:
            payload = self._context_payload()
        except ValueError as error:
            self._show_error(error)
            return
        self._save_json_payload(
            payload,
            "grim-gleaner-profile-context.json",
            t("automation.context_dialog_title"),
        )

    def _copy_context(self) -> None:
        try:
            text = json.dumps(
                self._context_payload(), ensure_ascii=False, indent=2
            )
        except ValueError as error:
            self._show_error(error)
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.diagnostics.setPlainText(t("automation.context_copied"))

    def _save_json_payload(
        self,
        payload: dict[str, object],
        filename: str,
        title: str,
    ) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            title,
            str(self.output_root / filename),
            t("automation.json_filter"),
        )
        if not selected:
            return
        try:
            atomic_write_text(
                Path(selected),
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            )
        except OSError as error:
            self._show_error(error)
            return
        self.diagnostics.setPlainText(
            t("automation.saved", path=Path(selected))
        )

    def _choose_candidate(self, *, import_after_validation: bool) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            t("automation.candidate_dialog_title"),
            str(self.output_root),
            t("automation.json_filter"),
        )
        if not selected:
            return
        candidate_path = Path(selected)
        try:
            candidate = load_profile(candidate_path)
            if self.catalog is None:
                raise ValueError(t("automation.catalog_unavailable"))
            result = validate_profile_semantics(candidate, self.catalog)
        except (OSError, TypeError, ValueError) as error:
            self.diagnostics.setPlainText(
                t("automation.invalid_file", error=error)
            )
            return

        self.diagnostics.setPlainText(
            self._format_validation(candidate, result)
        )
        if not import_after_validation or not result.valid:
            return
        answer = QMessageBox.question(
            self,
            t("automation.confirm_title"),
            t(
                "automation.confirm_body",
                name=candidate.name,
                stats=len(candidate.weights),
                skills=len(candidate.skill_weights),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.import_requested.emit(candidate_path)

    def _format_validation(
        self,
        profile: BuildProfile,
        result: ProfileValidationResult,
    ) -> str:
        lines = [
            t(
                "automation.validation_summary",
                name=profile.name,
                status=(
                    t("automation.valid")
                    if result.valid
                    else t("automation.invalid")
                ),
                errors=len(result.errors),
                warnings=len(result.warnings),
            )
        ]
        for diagnostic in (*result.errors, *result.warnings):
            line = (
                f"{diagnostic.severity.upper()} {diagnostic.path}: "
                f"{diagnostic.message}"
            )
            if diagnostic.suggestions:
                line += " — " + t(
                    "automation.suggestions",
                    values=", ".join(diagnostic.suggestions),
                )
            lines.append(line)
        return "\n".join(lines)

    def set_import_result(self, success: bool, message: str) -> None:
        prefix = (
            t("automation.import_success")
            if success
            else t("automation.import_failed")
        )
        self.diagnostics.appendPlainText(f"\n{prefix}: {message}")
        if success:
            self.refresh_from_profile()

    def _show_error(self, error: object) -> None:
        QMessageBox.critical(
            self,
            t("automation.error_title"),
            str(error),
        )
