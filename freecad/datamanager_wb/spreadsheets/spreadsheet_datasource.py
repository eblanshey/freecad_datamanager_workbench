# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Spreadsheet-backed `TabDataSource` for the Aliases tab.

Adapts spreadsheet alias queries/mutations to the generic `TabController`.

Parents are listed from the active document only. Reference counts and
expression items cover the whole reference search (every open document plus
the scope's closed ``.FCStd`` files); hits from outside the owner document
render document-qualified. Mutations are only attempted for spreadsheets in
documents that are actually loaded.
"""

from collections.abc import Callable

from ..domain.expression_item import ExpressionItem
from ..domain.parent_child_ref import ParentChildRef, parse_parent_child_ref
from ..domain.qualified_parent import split_parent_name
from ..domain.reference_hit import ReferenceHit
from ..domain.tab_datasource import RemoveUnusedResult, TabDataSource
from ..ports.freecad_context import FreeCadContext
from ..scanning.scanner import DocumentScanner
from ..scanning.scope import DocumentScope
from .spreadsheet_mutations import removeSpreadsheetAlias
from .spreadsheet_query import (
    find_sheet,
    getSpreadsheetAliasNames,
    getSpreadsheetAliasReferences,
    getSpreadsheets,
)


def _normalize_rhs(rhs: object) -> str:
    normalized_rhs = str(rhs).strip()
    if normalized_rhs.startswith("="):
        normalized_rhs = normalized_rhs[1:].lstrip()
    return normalized_rhs


def _is_alias_definition(*, object_name: str, parent: str, alias: str, rhs_text: str) -> bool:
    if object_name != parent:
        return False
    if not rhs_text.startswith("'"):
        return False
    return rhs_text.lstrip("'") == alias


def _to_expression_item(
    *,
    parent: str,
    alias: str,
    lhs: str,
    rhs: object,
    hit: ReferenceHit,
) -> ExpressionItem:
    object_name = lhs.split(".", 1)[0].strip()
    normalized_rhs = _normalize_rhs(rhs)
    definition = _is_alias_definition(
        object_name=object_name, parent=parent, alias=alias, rhs_text=normalized_rhs
    )
    operator = ":=" if definition else "="
    external = hit.is_external
    doc_id = hit.doc_id if external else None
    doc_label = (hit.doc_label or hit.doc_id) if external else None
    doc_path = hit.file_path if (external and hit.is_from_closed_document) else None
    return ExpressionItem(
        object_name=object_name,
        lhs=lhs,
        rhs=normalized_rhs,
        operator=operator,
        doc_id=doc_id,
        doc_label=doc_label,
        doc_path=doc_path,
    )


class SpreadsheetDataSource(TabDataSource):
    """Adapter that exposes spreadsheet aliases through the `TabDataSource` protocol.

    Args:
        ctx: Optional FreeCAD runtime context.
        scope_provider: Optional callable returning the current document scope.
        scanner: Optional shared scanner (provides the closed-file cache).
    """

    def __init__(
        self,
        *,
        ctx: FreeCadContext | None = None,
        scope_provider: Callable[[], DocumentScope] | None = None,
        scanner: DocumentScanner | None = None,
    ) -> None:
        self._ctx = ctx
        self._scope_provider = scope_provider
        self._scanner = scanner

    def _scope(self) -> DocumentScope:
        return self._scope_provider() if self._scope_provider else DocumentScope.empty()

    def get_sorted_parents(self, *, exclude_copy_on_change: bool = False) -> list[str]:
        """Return sorted spreadsheet names from the active document."""
        return sorted(
            getSpreadsheets(
                exclude_copy_on_change=exclude_copy_on_change,
                ctx=self._ctx,
                scope=self._scope(),
                scanner=self._scanner,
            )
        )

    def get_child_refs(self, selected_parents: list[str]) -> list[ParentChildRef]:
        """Return alias refs for the selected spreadsheets."""
        items: list[ParentChildRef] = []
        for sheet_name in selected_parents:
            for alias_name in getSpreadsheetAliasNames(
                sheet_name, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            ):
                items.append(ParentChildRef(parent=sheet_name, child=alias_name))
        items.sort(key=lambda ref: ref.text)
        return items

    def get_expression_items(
        self, selected_children: list[ParentChildRef] | list[str]
    ) -> tuple[list[ExpressionItem], dict[str, int]]:
        """Return expression items referencing the selected aliases."""
        counts: dict[str, int] = {}
        expression_items: list[ExpressionItem] = []
        for ref in _normalize_alias_refs(selected_children):
            _doc_id, bare_parent = split_parent_name(ref.parent)
            hits = getSpreadsheetAliasReferences(
                ref.parent, ref.child, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
            counts[ref.text] = len(hits)
            for hit in hits:
                expression_items.append(
                    _to_expression_item(
                        parent=bare_parent, alias=ref.child, lhs=hit.lhs, rhs=hit.rhs,
                        hit=hit,
                    )
                )

        expression_items.sort(key=lambda item: item.display_text)
        return expression_items, counts

    def get_expression_reference_counts(
        self, selected_children: list[ParentChildRef] | list[str]
    ) -> dict[str, int]:
        """Return expression reference counts for the selected aliases."""
        counts: dict[str, int] = {}
        for ref in _normalize_alias_refs(selected_children):
            hits = getSpreadsheetAliasReferences(
                ref.parent, ref.child, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
            counts[ref.text] = len(hits)
        return counts

    def remove_unused_children(
        self, selected_children: list[ParentChildRef] | list[str]
    ) -> RemoveUnusedResult:
        """Remove selected aliases that have no expression references.

        Aliases in closed (scanned) documents cannot be modified and are
        reported as failed.
        """
        removed: list[str] = []
        still_used: list[str] = []
        failed: list[str] = []

        for ref in _normalize_alias_refs(selected_children):
            hits = getSpreadsheetAliasReferences(
                ref.parent, ref.child, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
            if hits:
                still_used.append(ref.text)
                continue
            resolved = find_sheet(
                ref.parent, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
            if resolved is None or not resolved[0].is_open or resolved[0].document is None:
                failed.append(ref.text)
                continue
            ok = removeSpreadsheetAlias(
                resolved[1].name, ref.child, ctx=self._ctx, doc=resolved[0].document
            )
            if ok:
                removed.append(ref.text)
            else:
                failed.append(ref.text)

        return RemoveUnusedResult(removed=removed, still_used=still_used, failed=failed)


def _normalize_alias_refs(items: list[ParentChildRef] | list[str]) -> list[ParentChildRef]:
    normalized: list[ParentChildRef] = []
    for item in items:
        if isinstance(item, ParentChildRef):
            normalized.append(item)
        else:
            parsed = parse_parent_child_ref(item)
            if parsed is not None:
                normalized.append(parsed)
    return normalized
