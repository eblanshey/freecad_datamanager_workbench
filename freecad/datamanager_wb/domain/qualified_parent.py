# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Helpers for document-qualified parent names.

In cross-document scopes, parent list entries (VarSets / Spreadsheets) are
qualified with their owning document as ``Document#ObjectName`` so entries from
different documents stay unique. Inside a single-document scope the plain
``ObjectName`` form is used. This mirrors FreeCAD's own cross-document
expression syntax (``Document#Object.Property``).
"""

from __future__ import annotations

import os
import re

DOC_SEPARATOR = "#"


def qualify_parent_name(doc_id: str, name: str) -> str:
    """Return the `Document#Object` qualified form of a parent name."""
    return f"{doc_id}{DOC_SEPARATOR}{name}"


def split_parent_name(parent: str) -> tuple[str | None, str]:
    """Split a parent name into ``(doc_id, object_name)``.

    Returns ``(None, parent)`` when the name is not document-qualified.
    """
    if DOC_SEPARATOR in parent:
        doc_id, _, rest = parent.partition(DOC_SEPARATOR)
        if doc_id and rest:
            return doc_id, rest
    return None, parent


def document_id_from_path(path: str) -> str:
    """Return the identifier FreeCAD would use for a closed document's name.

    FreeCAD names a restored document after its file name stem, sanitized to a
    Python-identifier-like string. This approximates that rule for display and
    cross-document matching of closed files.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    ident = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    if not ident or ident[0].isdigit():
        ident = f"_{ident}"
    return ident
