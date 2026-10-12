# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Query helpers for FreeCAD VarSets.

Lists VarSets and their variables from the **active** document, and finds
expression references to a variable across **all** documents in the reference
search: every open document plus the closed ``.FCStd`` files of the
:class:`~..scanning.scope.DocumentScope`.

References from other documents use FreeCAD's cross-document syntax
(``Document#VarSet.var`` and label spellings); references inside the owning
document keep the familiar forms.
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
from ..scanning.scanner import DocumentScanner, ScanTarget, ScanVarSet
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


def getVarsets(
    *,
    exclude_copy_on_change: bool = False,
    ctx: FreeCadContext | None = None,
    scope: DocumentScope | None = None,
    scanner: DocumentScanner | None = None,
) -> Iterator[str]:
    """Yield VarSet names from the active document.

    Args:
        exclude_copy_on_change: When true, filters out VarSets that are created
            by FreeCAD's copy-on-change mechanism.
        ctx: Optional FreeCAD runtime context.
        scope: Ignored here (present for call-site symmetry); VarSets are
            listed from the active document only.
        scanner: Optional scanner instance (provides the closed-file cache).

    Yields:
        The `Name` of each `App::VarSet` object in the active document.
    """
    _ = scope
    target = _scanner(ctx, scanner).active_target()
    if target is None:
        return

    excluded = _excluded_copy_on_change_names(target) if exclude_copy_on_change else set()
    for varset in target.varsets:
        if exclude_copy_on_change and varset.name in excluded:
            continue
        yield varset.name


def _excluded_copy_on_change_names(target: ScanTarget) -> set[str]:
    if target.document is None:
        return set()
    return get_copy_on_change_names(doc=target.document, type_id="App::VarSet")


def find_varset(
    varset_spec: str,
    *,
    scope: DocumentScope | None = None,
    ctx: FreeCadContext | None = None,
    scanner: DocumentScanner | None = None,
    targets: list[ScanTarget] | None = None,
) -> tuple[ScanTarget, ScanVarSet] | None:
    """Resolve a (optionally qualified) varset name to target and data.

    Resolution prefers the active document, so a name that exists in several
    documents binds to the one the user is looking at. Qualified specs
    (``Document#VarSet``) resolve against the named document.

    Returns:
        ``(target, varset)`` or ``None`` when the varset cannot be found.
    """
    doc_id, varset_name = split_parent_name(varset_spec)
    scanner_impl = _scanner(ctx, scanner)

    if doc_id is None:
        active = scanner_impl.active_target()
        if active is not None:
            found = _varset_in(active, varset_name)
            if found is not None:
                return active, found

    if targets is None:
        targets = scanner_impl.resolve(scope or DocumentScope.empty())
    for target in targets:
        if doc_id is not None and target.doc_id != doc_id:
            continue
        found = _varset_in(target, varset_name)
        if found is not None:
            return target, found
    return None


def _varset_in(target: ScanTarget, varset_name: str) -> ScanVarSet | None:
    for varset in target.varsets:
        if varset.name == varset_name:
            return varset
    return None


def getVarsetVariableGroups(
    varset_spec: str,
    *,
    ctx: FreeCadContext | None = None,
    scope: DocumentScope | None = None,
    scanner: DocumentScanner | None = None,
) -> dict[str, str]:
    """Return mapping of variable/property name -> group for a VarSet."""
    resolved = find_varset(varset_spec, ctx=ctx, scope=scope, scanner=scanner)
    if resolved is None:
        return {}
    _target, varset = resolved
    return dict(varset.variables)


def getVarsetVariableNames(
    varset_spec: str,
    *,
    ctx: FreeCadContext | None = None,
    scope: DocumentScope | None = None,
    scanner: DocumentScanner | None = None,
) -> list[str]:
    """Return sorted variable/property names defined on a VarSet.

    Built-in FreeCAD properties (Label, Placement, etc.) are excluded.
    """
    groups = getVarsetVariableGroups(varset_spec, ctx=ctx, scope=scope, scanner=scanner)
    return sorted(groups)


def getVarsetVariableNamesForGroup(
    varset_spec: str,
    group_name: str | None,
    *,
    ctx: FreeCadContext | None = None,
    scope: DocumentScope | None = None,
    scanner: DocumentScanner | None = None,
) -> list[str]:
    """Return variable names on a VarSet, optionally filtered by group."""
    groups = getVarsetVariableGroups(varset_spec, ctx=ctx, scope=scope, scanner=scanner)
    if not group_name:
        return sorted(groups)
    wanted = group_name.strip() or "Base"
    return sorted(n for n in groups if groups.get(n, "Base") == wanted)


def getVarsetReferences(
    varset_spec: str,
    variable_name: str | None = None,
    *,
    ctx: FreeCadContext | None = None,
    scope: DocumentScope | None = None,
    scanner: DocumentScanner | None = None,
) -> list[ReferenceHit]:
    """Find expressions (and cells) referencing a VarSet or one variable.

    Searches the entire reference set: all open documents plus the scope's
    closed files. Same-document references match ``VarSet.var`` /
    ``<<Label>>.var`` (plus bare sibling names inside the VarSet's own
    expressions); references from other documents must use FreeCAD's
    cross-document ``Document#VarSet.var`` syntax (name or label spellings).

    Args:
        varset_spec: VarSet name, optionally ``Document#``-qualified.
        variable_name: Optional variable name to scope matches. When omitted,
            any expression referencing the VarSet counts.

    Returns:
        List of :class:`ReferenceHit` records, owner document first.
    """
    targets = _search_targets(scope=scope, ctx=ctx, scanner=scanner)
    resolved = find_varset(varset_spec, ctx=ctx, scope=scope, scanner=scanner, targets=targets)
    if resolved is None:
        return []
    owner_target, varset = resolved

    target = ReferenceTarget(
        doc_id=owner_target.doc_id,
        doc_label=owner_target.label,
        object_name=varset.name,
        object_label=varset.label,
        child=variable_name,
    )

    hits: list[ReferenceHit] = []
    for scan_target in targets:
        for entry in scan_target.entries:
            if entry_matches_target(entry, target):
                hits.append(_hit_from_entry(scan_target, entry, owner_doc_id=target.doc_id))

    return _dedupe_sorted(hits, owner_doc_id=target.doc_id)


def _dedupe_sorted(hits: list[ReferenceHit], *, owner_doc_id: str) -> list[ReferenceHit]:
    """Owner-document hits first, then the rest; stable and duplicate-free."""
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
