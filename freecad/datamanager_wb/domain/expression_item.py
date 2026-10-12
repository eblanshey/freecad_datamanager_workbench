# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Lightweight representation of an expression binding.

This module defines a small dataclass used to display and select expression
engine entries in the UI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpressionItem:
    """A single expression binding shown in the UI.

    Instances represent one expression assignment (left-hand side and right-hand
    side) that belongs to a particular FreeCAD object. The UI uses these items
    to populate the expressions list and to select the referenced object when a
    user clicks an entry.

    Attributes:
        object_name: Name/label of the FreeCAD object that owns the expression.
        lhs: Left-hand side of the expression (typically "Object.Property").
        rhs: Right-hand side expression string.
        operator: Infix operator shown between `lhs` and `rhs` in the UI.
        doc_id: Identifier of the referencing document. Set only for hits that
            live outside the document owning the selected variable, so those
            entries render as ``Document.Object.Property``.
        doc_label: Display label of the referencing document (falls back to
            `doc_id` in name mode).
        doc_path: File path of a closed referencing document, used to open the
            document when the user jumps to the reference.
    """

    object_name: str
    lhs: str
    rhs: str
    operator: str = "="
    doc_id: str | None = None
    doc_label: str | None = None
    doc_path: str | None = None

    @property
    def display_text(self) -> str:
        """Return the display string shown in the expressions list."""
        if self.doc_id:
            doc_token = self.doc_label or self.doc_id
            return f"{doc_token}.{self.lhs} {self.operator} {self.rhs}"
        return f"{self.lhs} {self.operator} {self.rhs}"
