# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Query helpers for spreadsheet aliases.

Lists spreadsheets and their aliases from the **active** document, and finds
expressions/cells referencing an alias across **all** documents in the
reference search: every open document plus the closed ``.FCStd`` files of the
:class:`~..scanning.scope.DocumentScope`.

Document reading (live aliases, cell contents, closed-file parsing) lives in
:mod:`..scanning.scanner`; this module implements only the query surface. The
alias-map normalization helpers it once owned now live in
:mod:`..scanning.scanner` and are re-exported here for callers that used the
private names.
"""

from __future__ import annotations

from collections.abc import Iterator

from ..domain.expression_entry import ExpressionEntry
from ..domain.qualified_parent import split_parent_name
from ..domain.reference_hit import SOURCE_FILE, SOURCE_OPEN, ReferenceHit
from ..freecad_helpers import get_copy_on_change_names
from ..ports.freecad_context import FreeCadContext
from ..ports.freecad_port import get_port
from ..scanning.reference_match import ReferenceTarget, entry_matches_target
from ..scanning.scanner import (
    DocumentScanner,
    ScanSheet,
    ScanTarget,
)
from ..scanning.scanner import (
    _normalize_alias_map as _normalize_alias_map,  # re-export: kept for callers/tests
)
from ..scanning.scope import DocumentScope


def _scanner(
    ctx: FreeCadContext | None, scanner: DocumentScanner | None
) -> DocumentScanner:
    return scanner or DocumentScanner(get_port(ctx))


def _search_targets(
    *,
    scope: DocumentScope | None,
    ctx: FreeCadContext | None,
    scanner: DocumentScanner | None,
) -> list[ScanTarget]:
    return _scanner(ctx, scanner).resolve(scope or DocumentScope.empty())


def _excluded_copy_on_change_names(target: ScanTarget) -> set[str]:
    if target.document is None:
        return set()
    return get_copy_on_change_names(doc=target.document, type_id="Spreadsheet::Sheet")


def getSpreadsheets(
    *,
    exclude_copy_on_change: bool = False,
    ctx: FreeCadContext | None = None,
    scope: DocumentScope | None = None,
    scanner: DocumentScanner | None = None,
) -> Iterator[str]:
    """Yield spreadsheet names from the active document.

    Args:
        exclude_copy_on_change: When true, filters out spreadsheets created by
            FreeCAD's copy-on-change mechanism.
        scope: Ignored here (present for call-site symmetry); spreadsheets are
            listed from the active document only.

    Yields:
        The `Name` of each `Spreadsheet::Sheet` object in the active document.
    """
    _ = scope
    target = _scanner(ctx, scanner).active_target()
    if target is None:
        return

    excluded = _excluded_copy_on_change_names(target) if exclude_copy_on_change else set()
    for sheet in target.sheets:
        if exclude_copy_on_change and sheet.name in excluded:
            continue
        yield sheet.name


def find_sheet(
    sheet_spec: str,
    *,
    scope: DocumentScope | None = None,
    ctx: FreeCadContext | None = None,
    scanner: DocumentScanner | None = None,
    targets: list[ScanTarget] | None = None,
) -> tuple[ScanTarget, ScanSheet] | None:
    """Resolve a (optionally qualified) sheet name to target and data.

    Resolution prefers the active document. Qualified specs
    (``Document#Sheet``) resolve against the named document.
    """
    doc_id, sheet_name = split_parent_name(sheet_spec)
    scanner_impl = _scanner(ctx, scanner)

    if doc_id is None:
        active = scanner_impl.active_target()
        if active is not None:
            found = _sheet_in(active, sheet_name)
            if found is not None:
                return active, found

    if targets is None:
        targets = scanner_impl.resolve(scope or DocumentScope.empty())
    for target in targets:
        if doc_id is not None and target.doc_id != doc_id:
            continue
        found = _sheet_in(target, sheet_name)
        if found is not None:
            return target, found
    return None


def _sheet_in(target: ScanTarget, sheet_name: str) -> ScanSheet | None:
    for sheet in target.sheets:
        if sheet.name == sheet_name:
            return sheet
    return None


def getSpreadsheetAliasNames(
    sheet_spec: str,
    *,
    ctx: FreeCadContext | None = None,
    scope: DocumentScope | None = None,
    scanner: DocumentScanner | None = None,
) -> list[str]:
    """Return all alias names defined on a spreadsheet, sorted."""
    resolved = find_sheet(sheet_spec, ctx=ctx, scope=scope, scanner=scanner)
    if resolved is None:
        return []
    _target, sheet = resolved
    return sorted(sheet.aliases)


def getSpreadsheetAliasReferences(
    sheet_spec: str,
    alias_name: str | None = None,
    *,
    ctx: FreeCadContext | None = None,
    scope: DocumentScope | None = None,
    scanner: DocumentScanner | None = None,
) -> list[ReferenceHit]:
    """Find expressions and cells that reference a spreadsheet or one alias.

    The entire reference set is searched: all open documents plus the scope's
    closed files. Same-document references match ``Sheet.alias`` /
    ``<<Sheet Label>>.alias`` (plus word-boundary mentions inside the owning
    sheet's cells — the alias definition cell itself shows up as a `:=` row in
    the UI). References from other documents use the cross-document
    ``Document#Sheet.alias`` syntax.

    Args:
        sheet_spec: Sheet name, optionally `Document#`-qualified.
        alias_name: Optional alias name. When provided, searches for references
            to that alias; otherwise searches for references to the spreadsheet.

    Returns:
        List of :class:`ReferenceHit` records, owner document first.
    """
    targets = _search_targets(scope=scope, ctx=ctx, scanner=scanner)
    resolved = find_sheet(sheet_spec, ctx=ctx, scope=scope, scanner=scanner, targets=targets)
    if resolved is None:
        return []
    owner_target, sheet = resolved

    target = ReferenceTarget(
        doc_id=owner_target.doc_id,
        doc_label=owner_target.label,
        object_name=sheet.name,
        object_label=sheet.label,
        child=alias_name,
    )

    hits: list[ReferenceHit] = []
    for scan_target in targets:
        for entry in scan_target.entries:
            if entry_matches_target(entry, target):
                hits.append(_hit_from_entry(scan_target, entry, owner_doc_id=target.doc_id))

    return _dedupe_sorted(hits, owner_doc_id=target.doc_id)


def _dedupe_sorted(hits: list[ReferenceHit], *, owner_doc_id: str) -> list[ReferenceHit]:
    hits.sort(key=lambda hit: (0 if hit.doc_id == owner_doc_id else 1, hit.lhs, hit.rhs))
    seen: set[tuple[str, str, str]] = set()
    unique: list[ReferenceHit] = []
    for hit in hits:
        key = (hit.doc_id, hit.lhs, hit.rhs)
        if key in seen:
            continue
        seen.add(key)
        unique.append(hit)
    return unique


def _hit_from_entry(
    scan_target: ScanTarget, entry: ExpressionEntry, *, owner_doc_id: str
) -> ReferenceHit:
    return ReferenceHit(
        doc_id=scan_target.doc_id,
        doc_label=scan_target.label,
        owner_doc_id=owner_doc_id,
        source=SOURCE_OPEN if scan_target.is_open else SOURCE_FILE,
        file_path=scan_target.file_path,
        object_name=entry.object_name,
        lhs=entry.binding_key(),
        rhs=entry.rhs,
    )


__all__ = [
    "DocumentScanner",
    "ReferenceHit",
    "ScanSheet",
    "ScanTarget",
    "find_sheet",
    "getSpreadsheetAliasNames",
    "getSpreadsheetAliasReferences",
    "getSpreadsheets",
]
