# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Reference hit records returned by cross-document queries."""

from __future__ import annotations

from dataclasses import dataclass

SOURCE_OPEN = "open"
SOURCE_FILE = "file"


@dataclass(frozen=True)
class ReferenceHit:
    """One expression reference to a VarSet variable or spreadsheet alias.

    Attributes:
        doc_id: Identifier of the document that contains the referencing
            expression (open document name or closed-file identifier).
        doc_label: Display label of that document.
        owner_doc_id: Identifier of the document that owns the referenced
            VarSet/alias. Hits where `doc_id != owner_doc_id` are external
            usages and are rendered document-qualified.
        source: `SOURCE_OPEN` when the referencing document is loaded,
            `SOURCE_FILE` when it was found by scanning a closed ``.FCStd``.
        file_path: Absolute path of the referencing document's file, when the
            scan produced one.
        object_name: Name of the object owning the referencing expression.
        lhs: Binding key (`Object.Property` or `Sheet.A1`) of the reference.
        rhs: The referencing expression / cell text.
    """

    doc_id: str
    doc_label: str
    owner_doc_id: str
    source: str
    file_path: str | None
    object_name: str
    lhs: str
    rhs: str

    @property
    def is_from_closed_document(self) -> bool:
        """Return True when this hit lives in a closed document."""
        return self.source == SOURCE_FILE

    @property
    def is_external(self) -> bool:
        """Return True when the reference lives outside the owner document."""
        return self.doc_id != self.owner_doc_id
