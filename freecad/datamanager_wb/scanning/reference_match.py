# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Pattern matching rules for finding references to VarSets and spreadsheet
aliases inside scanned expression text.

FreeCAD expressions reference variables in three ways, all handled here:

1. **Same document** — ``VarSet.height``, ``<<Var Label>>.height`` or (inside the
   VarSet itself) a bare word-boundary ``height`` occurrence.
2. **Cross document** — FreeCAD's xlink syntax
   ``DocName#Object.Property`` / ``<<Doc Label>>#Object.Property`` /
   ``"Doc Label"#Object.Property``; these are *the only* forms matched in
   documents other than the target's owner, to avoid false positives between
   documents with colliding object names.
3. **Spreadsheet cells** — non-empty cell contents are matched with the same
   rules (formulas may reference aliases or cross-document properties).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from ..domain.expression_entry import ExpressionEntry

_TRAILING: Final = r"(?![A-Za-z0-9_])"


@dataclass(frozen=True)
class ReferenceTarget:
    """What a reference query looks for.

    Attributes:
        doc_id: Identifier of the document that owns the target
            (VarSet or spreadsheet object).
        doc_label: Display label of the owning document.
        object_name: Internal name of the target object.
        object_label: Label of the target object.
        child: Optional variable/alias name; when ``None`` any reference to the
            target object counts.
    """

    doc_id: str
    doc_label: str
    object_name: str
    object_label: str
    child: str | None = None

    @property
    def is_whole_object(self) -> bool:
        """Return True when the query targets the whole object, not one child."""
        return self.child is None


def _identifier_tokens(name: str, label: str) -> tuple[str, ...]:
    """Return all identifier spellings that may refer to an object/document."""
    tokens = [name]
    for text in (label, name):
        if not text:
            continue
        for candidate in (f"<<{text}>>", f'"{text}"'):
            if candidate not in tokens:
                tokens.append(candidate)
    return tuple(tokens)


def _object_tokens(target: ReferenceTarget) -> tuple[str, ...]:
    return _identifier_tokens(target.object_name, target.object_label)


def _doc_tokens(target: ReferenceTarget) -> tuple[str, ...]:
    return _identifier_tokens(target.doc_id, target.doc_label)


def _with_child(token: str, child: str | None) -> str:
    if child is None:
        return token
    return f"{token}.{child}"


def same_document_patterns(target: ReferenceTarget) -> tuple[re.Pattern[str], ...]:
    """Return patterns matching references inside the owning document.

    Whole-object queries keep the historical exact ``<<Label>>``-style forms.
    Whole-object queries also match the plain ``Object`` token (e.g. a
    spreadsheet referenced as ``Sheet.A1``).
    """
    patterns: list[re.Pattern[str]] = []
    for token in _object_tokens(target):
        literal = re.escape(_with_child(token, target.child))
        if target.child is not None:
            patterns.append(re.compile(literal + _TRAILING))
        elif token.startswith("<<") or token.startswith('"'):
            # Bracketed/quoted label spellings are exact on their own.
            patterns.append(re.compile(literal))
        else:
            # A bare internal name only counts as a whole-object reference when
            # it starts a binding path (`Object.`), not as a loose substring.
            patterns.append(re.compile(literal + r"\."))
    return tuple(patterns)


def cross_document_patterns(target: ReferenceTarget) -> tuple[re.Pattern[str], ...]:
    """Return patterns matching ``Doc#Object[.child]`` references.

    The trailing identifier guard prevents ``Doc#VarSet`` from matching
    ``Doc#VarSet001``.
    """
    patterns: list[re.Pattern[str]] = []
    for doc in _doc_tokens(target):
        for obj in _object_tokens(target):
            text = _with_child(f"{doc}#{obj}", target.child)
            patterns.append(re.compile(re.escape(text) + _TRAILING))
    return tuple(patterns)


def internal_child_pattern(target: ReferenceTarget) -> re.Pattern[str] | None:
    """Return the word-boundary pattern for a VarSet's own expression entries.

    Inside a VarSet, sibling variables are referenced by their bare name, so a
    variable is considered referenced when the word appears in the VarSet's own
    expressions (same rule the workbench used for the active document).
    """
    if target.child is None:
        return None
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(target.child)}{_TRAILING}")


def entry_matches_target(entry: ExpressionEntry, target: ReferenceTarget) -> bool:
    """Return True when a scanned entry references the target."""
    text = str(entry.rhs)
    if entry.source_doc == target.doc_id:
        return _same_doc_entry_matches(entry, target, text)
    return _cross_doc_entry_matches(target, text)


def _same_doc_entry_matches(entry: ExpressionEntry, target: ReferenceTarget, text: str) -> bool:
    for pattern in same_document_patterns(target):
        if pattern.search(text):
            return True
    internal = internal_child_pattern(target)
    if internal is not None and entry.object_name == target.object_name:
        if internal.search(text):
            return True
    return False


def _cross_doc_entry_matches(target: ReferenceTarget, text: str) -> bool:
    for pattern in cross_document_patterns(target):
        if pattern.search(text):
            return True
    return False
