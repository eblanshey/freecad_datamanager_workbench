# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""VarSet-backed `TabDataSource` for the VarSets tab.

Adapts varset document-model operations to the generic `TabController`.

Parents are listed from the active document only. Reference counts and
expression items cover the whole reference search (every open document plus
the scope's closed ``.FCStd`` files); hits from outside the owner document
render document-qualified. Mutations are only attempted for VarSets in
documents that are actually loaded.
"""

from collections.abc import Callable

from ..domain.expression_item import ExpressionItem
from ..domain.parent_child_ref import ParentChildRef, normalize_parent_child_items
from ..domain.parsing_helpers import parse_varset_variable_item
from ..domain.qualified_parent import split_parent_name
from ..domain.reference_hit import ReferenceHit
from ..domain.tab_datasource import RemoveUnusedResult, TabDataSource
from ..ports.freecad_context import FreeCadContext
from ..scanning.scanner import DocumentScanner
from ..scanning.scope import DocumentScope
from .varset_mutations import removeVarsetVariable
from .varset_query import (
    find_varset,
    getVarsetReferences,
    getVarsets,
    getVarsetVariableGroups,
    getVarsetVariableNames,
    getVarsetVariableNamesForGroup,
)


class VarsetDataSource(TabDataSource):
    """Adapter that exposes VarSets through the `TabDataSource` protocol.

    This class maps generic tab operations (parents, children, expression
    queries, remove-unused) onto the VarSet-specific document model.

    Args:
        ctx: Optional FreeCAD runtime context.
        scope_provider: Optional callable returning the current document
            scope (the panel controller owns scope changes at runtime).
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
        """Return sorted VarSet names from the active document.

        If a VarSet contains variables in more than one group, also include
        virtual VarSet entries of the form "{varset}.{group}".
        """
        parents: list[str] = []
        for varset_name in sorted(
            getVarsets(
                exclude_copy_on_change=exclude_copy_on_change,
                ctx=self._ctx,
                scope=self._scope(),
                scanner=self._scanner,
            )
        ):
            parents.append(varset_name)

            groups = set(
                getVarsetVariableGroups(
                    varset_name, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
                ).values()
            )
            if len(groups) <= 1:
                continue
            for group in sorted(groups):
                parents.append(f"{varset_name}.{group}")
        return parents

    def _get_varset_groups(self, varset_name: str) -> set[str]:
        return set(
            getVarsetVariableGroups(
                varset_name, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            ).values()
        )

    def _split_virtual_parent(self, text: str) -> tuple[str, str] | None:
        if "." not in text:
            return None
        varset_name, group = text.split(".", 1)
        if not varset_name or not group:
            return None
        return varset_name, group

    def _parse_virtual_varset(self, text: str) -> tuple[str, str] | None:
        parsed = self._split_virtual_parent(text)
        if parsed is None:
            return None
        varset_name, group = parsed

        groups = self._get_varset_groups(varset_name)
        if len(groups) <= 1 or group not in groups:
            return None
        return parsed

    def _get_var_names_for_parent(self, parent: str) -> tuple[str, list[str]]:
        parsed_virtual = self._parse_virtual_varset(parent)
        if parsed_virtual is None:
            return parent, getVarsetVariableNames(
                parent, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
        varset_name, group = parsed_virtual
        return varset_name, getVarsetVariableNamesForGroup(
            varset_name, group, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
        )

    def get_child_refs(self, selected_parents: list[str]) -> list[ParentChildRef]:
        """Return variable refs for the selected VarSets."""
        variable_items: list[str] = []
        for parent in selected_parents:
            varset_name, var_names = self._get_var_names_for_parent(parent)

            for var_name in var_names:
                variable_items.append(f"{varset_name}.{var_name}")

        variable_items.sort()
        refs: list[ParentChildRef] = []
        for text in variable_items:
            parsed = parse_varset_variable_item(text)
            if parsed is None:
                continue
            parent, child = parsed
            refs.append(ParentChildRef(parent=parent, child=child))
        return refs

    def get_expression_items(
        self, selected_children: list[ParentChildRef] | list[str]
    ) -> tuple[list[ExpressionItem], dict[str, int]]:
        """Return expression items referencing the selected variables."""
        expression_items: list[ExpressionItem] = []
        counts: dict[str, int] = {}

        for text in normalize_parent_child_items(selected_children):
            parsed = parse_varset_variable_item(text)
            if parsed is None:
                continue
            varset_name, variable_name = parsed
            hits = getVarsetReferences(
                varset_name, variable_name, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
            counts[text] = len(hits)
            for hit in hits:
                expression_items.append(_to_expression_item(hit))

        expression_items.sort(key=lambda item: item.display_text)
        return expression_items, counts

    def get_expression_reference_counts(
        self, selected_children: list[ParentChildRef] | list[str]
    ) -> dict[str, int]:
        """Return expression reference counts for the selected variables."""
        counts: dict[str, int] = {}

        for text in normalize_parent_child_items(selected_children):
            parsed = parse_varset_variable_item(text)
            if parsed is None:
                continue
            varset_name, variable_name = parsed
            hits = getVarsetReferences(
                varset_name, variable_name, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
            counts[text] = len(hits)

        return counts

    def remove_unused_children(
        self, selected_children: list[ParentChildRef] | list[str]
    ) -> RemoveUnusedResult:
        """Remove variables that have no expression references.

        A variable is only removed when its VarSet lives in a loaded document;
        variables in closed (scanned) documents are reported as failed.
        """
        removed: list[str] = []
        still_used: list[str] = []
        failed: list[str] = []

        for text in normalize_parent_child_items(selected_children):
            parsed = parse_varset_variable_item(text)
            if parsed is None:
                failed.append(text)
                continue
            varset_name, variable_name = parsed
            hits = getVarsetReferences(
                varset_name, variable_name, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
            if hits:
                still_used.append(text)
                continue
            resolved = find_varset(
                varset_name, ctx=self._ctx, scope=self._scope(), scanner=self._scanner
            )
            if resolved is None:
                failed.append(text)
                continue
            target, varset = resolved
            if not target.is_open or target.document is None:
                failed.append(text)
                continue
            ok = removeVarsetVariable(
                varset.name, variable_name, ctx=self._ctx, doc=target.document
            )
            if ok:
                removed.append(text)
            else:
                failed.append(text)

        return RemoveUnusedResult(removed=removed, still_used=still_used, failed=failed)

    def _varset_is_mutable(self, varset_name: str) -> bool:
        resolved = find_varset(varset_name, ctx=self._ctx, scope=self._scope(), scanner=self._scanner)
        return resolved is not None and resolved[0].is_open


def _to_expression_item(hit: ReferenceHit) -> ExpressionItem:
    """Convert a reference hit into a UI expression item.

    Hits from outside the owner document carry the referencing document's
    identity so the list renders them as ``Document.Object.Property``; same
    document hits stay plain.
    """
    if not hit.is_external:
        return ExpressionItem(object_name=hit.object_name, lhs=hit.lhs, rhs=hit.rhs)
    return ExpressionItem(
        object_name=hit.object_name,
        lhs=hit.lhs,
        rhs=hit.rhs,
        doc_id=hit.doc_id,
        doc_label=hit.doc_label or hit.doc_id,
        doc_path=hit.file_path if hit.is_from_closed_document else None,
    )


__all__ = ["VarsetDataSource", "split_parent_name"]
