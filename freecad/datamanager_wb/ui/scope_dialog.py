# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Closed-document picker for the reference search.

All open documents are always searched. This dialog manages the additional
**closed** ``.FCStd`` files (by absolute path) to scan. Chosen files are parsed
statically; nothing is opened in FreeCAD until the user jumps to a reference
inside one.
"""

from __future__ import annotations

import os

from PySide import QtCore, QtWidgets

from ..ports.app_port import AppPort


class ReferenceFilesDialog(QtWidgets.QDialog):
    """Qt dialog collecting additional closed documents to search.

    Args:
        app_port: Translation port.
        files: Initial list of closed ``.FCStd`` paths.
        parent: Optional Qt parent widget.
    """

    def __init__(
        self,
        *,
        app_port: AppPort,
        files: list[str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._app_port = app_port
        self.setWindowTitle(app_port.translate("Workbench", "Additional reference documents"))
        self.resize(520, 360)

        self._list_widget = QtWidgets.QListWidget(self)
        self._list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        for path in files:
            self._add_row(path)

        add_button = QtWidgets.QPushButton(
            app_port.translate("Workbench", "Add files…"), self
        )
        remove_button = QtWidgets.QPushButton(
            app_port.translate("Workbench", "Remove selected"), self
        )
        add_button.clicked.connect(self._on_add_files)
        remove_button.clicked.connect(self._on_remove_selected)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        row_buttons = QtWidgets.QHBoxLayout()
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch(1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                app_port.translate(
                    "Workbench",
                    "All open documents are always searched. Add closed "
                    "FreeCAD files to search them as well:",
                ),
                self,
            )
        )
        layout.addWidget(self._list_widget)
        layout.addLayout(row_buttons)
        layout.addWidget(button_box)

    def _add_row(self, path: str) -> None:
        item = QtWidgets.QListWidgetItem(os.path.basename(path))
        item.setToolTip(path)
        item.setData(QtCore.Qt.UserRole, path)
        self._list_widget.addItem(item)

    def _on_add_files(self) -> None:
        existing = self.selected_files()
        title = self._app_port.translate("Workbench", "Add FreeCAD documents")
        paths, _selected = QtWidgets.QFileDialog.getOpenFileNames(
            self, title, "", "FreeCAD documents (*.FCStd);;All files (*)"
        )
        for path in paths:
            abs_path = os.path.abspath(path)
            if abs_path in existing:
                continue
            self._add_row(abs_path)

    def _on_remove_selected(self) -> None:
        for item in self._list_widget.selectedItems():
            self._list_widget.takeItem(self._list_widget.row(item))

    def selected_files(self) -> list[str]:
        """Return the absolute paths of all listed files."""
        files: list[str] = []
        for index in range(self._list_widget.count()):
            item = self._list_widget.item(index)
            if item is None:
                continue
            value = item.data(QtCore.Qt.UserRole)
            if isinstance(value, str) and value:
                files.append(value)
        return files
