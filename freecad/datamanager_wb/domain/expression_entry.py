# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Normalized expression text records produced by document scanners.

A scanner (live document or static ``.FCStd`` file) emits :class:`ExpressionEntry`
records for every piece of text that can contain a reference:

- expression engine bindings of any document object (`kind == "expression"`), and
- non-empty spreadsheet cells (`kind == "cell"`, `lhs` is the cell address).

The reference matcher in :mod:`..scanning.reference_match` consumes these records,
which keeps matching logic independent of whether the source document is open or
closed.
"""

from __future__ import annotations

from dataclasses import dataclass

ENTRY_KIND_EXPRESSION = "expression"
ENTRY_KIND_CELL = "cell"


@dataclass(frozen=True)
class ExpressionEntry:
    """One searchable text record owned by a document object.

    Attributes:
        source_doc: Document identifier that produced this entry (open document
            `Name`, or the file-name-derived identifier for closed documents).
        kind: `ENTRY_KIND_EXPRESSION` or `ENTRY_KIND_CELL`.
        object_name: Name of the owning document object (VarSet, sheet, ...).
        lhs: Binding path relative to the object (expression `Path`) or the cell
            address for cell entries.
        rhs: The searchable text (expression string or cell contents).
        object_label: Owner label for display, when available.
    """

    source_doc: str
    kind: str
    object_name: str
    lhs: str
    rhs: str
    object_label: str = ""

    def binding_key(self) -> str:
        """Return the canonical `Object.Path` / `Object.Cell` display key."""
        if self.kind == ENTRY_KIND_CELL:
            return f"{self.object_name}.{self.lhs}"
        if self.lhs.startswith("."):
            return f"{self.object_name}{self.lhs}"
        return f"{self.object_name}.{self.lhs}"
