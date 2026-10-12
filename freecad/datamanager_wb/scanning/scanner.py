# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Resolve a :class:`~..scanning.scope.DocumentScope` into unified scan targets.

:class:`DocumentScanner` produces one :class:`ScanTarget` per document in the
scope. Open documents are read through the live FreeCAD port; closed files are
read statically with :mod:`.fcstd_file`. The result shape is identical either
way, so query code never branches on the document's open state.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from glob import glob
from typing import Any

from ..domain.expression_entry import ENTRY_KIND_CELL, ENTRY_KIND_EXPRESSION, ExpressionEntry
from ..domain.varset_builtin_properties import is_excluded_varset_property
from .fcstd_file import SHEET_TYPE_ID, VARSET_TYPE_ID, FcstdDocument, FcstdReadError, read_fcstd
from .scope import DocumentScope

VARSET_GROUP_GETTER_ATTR = "getGroupOfProperty"
SHEET_CELLS_ATTRS = ("getUsedCells", "getNonEmptyCells", "getCells")
_CELL_RE = re.compile(r"^[A-Z]+[0-9]+$")


@dataclass(frozen=True)
class ScanVarSet:
    """A VarSet in a scan target.

    Attributes:
        name: Object internal name.
        label: Object label.
        variables: Mapping of variable name -> property group.
    """

    name: str
    label: str
    variables: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScanSheet:
    """A spreadsheet in a scan target.

    Attributes:
        name: Object internal name.
        label: Object label.
        aliases: Mapping of alias name -> cell address.
    """

    name: str
    label: str
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScanTarget:
    """One document of the scan scope, from either source kind.

    Attributes:
        doc_id: Identifier used to qualify entries (open: document name,
            closed: file-name identifier).
        label: Display label.
        is_open: Whether the document is currently loaded in FreeCAD.
        file_path: Absolute file path when known (saved open documents and all
            closed-file targets).
        document: The live document object for open targets, else None.
        varsets: VarSets in the document.
        sheets: Spreadsheets in the document.
        entries: Expression engine entries and non-empty spreadsheet cells.
    """

    doc_id: str
    label: str
    is_open: bool
    file_path: str | None
    varsets: tuple[ScanVarSet, ...] = ()
    sheets: tuple[ScanSheet, ...] = ()
    entries: tuple[ExpressionEntry, ...] = ()
    document: object | None = None


class DocumentScanner:
    """Builds :class:`ScanTarget` lists for a document scope.

    Closed ``.FCStd`` files are parsed lazily and cached; the cache entry is
    invalidated when the file's mtime/size changes, so refreshes re-read only
    modified files.
    """

    def __init__(self, port: Any) -> None:  # noqa: ANN401 - port duck-typed for tests
        self._port = port
        self._file_cache: dict[str, tuple[float, int, FcstdDocument | None]] = {}

    def resolve(self, scope: DocumentScope) -> list[ScanTarget]:
        """Return the reference-search set for the scope.

        Always every open non-temporary document, plus the scope's closed
        files, plus every ``.FCStd`` file in the saved active document's
        directory tree (fcxref-style automatic project search). Files that
        belong to already-open documents are deduplicated (the live document
        wins).
        """
        targets = [
            self._live_target(doc) for doc in self._open_documents() if not _is_temporary(doc)
        ]
        known_ids = {target.doc_id for target in targets}
        known_paths = {target.file_path for target in targets if target.file_path}
        self._add_file_targets(scope.extra_files, targets, known_ids, known_paths)
        self._add_file_targets(self._project_folder_paths(), targets, known_ids, known_paths)
        return targets

    def _add_file_targets(
        self,
        paths: tuple[str, ...] | list[str],
        targets: list[ScanTarget],
        known_ids: set[str],
        known_paths: set[str],
    ) -> None:
        """Append deduplicated closed-file scan targets for ``paths``."""
        for path in paths:
            norm = _norm_path(path)
            if norm and norm in known_paths:
                continue
            target = self._file_target(path)
            if target is None or target.doc_id in known_ids:
                continue
            known_ids.add(target.doc_id)
            if target.file_path:
                known_paths.add(target.file_path)
            targets.append(target)

    def _project_folder_paths(self) -> list[str]:
        """Return every ``.FCStd`` in the saved active document's directory tree.

        Mirrors fcxref's recursive ``**/*.FCStd`` glob, rooted at the active
        document's on-disk location instead of the shell's cwd. Unsaved
        documents contribute no folder; hidden directories are skipped by
        ``glob``.
        """
        doc = self._port.get_active_document()
        if doc is None:
            return []
        file_name = _norm_path(_document_file_name(doc))
        if not file_name or not os.path.isfile(file_name):
            return []
        base = os.path.dirname(file_name)
        return sorted(glob(os.path.join(base, "**", "*.FCStd"), recursive=True))

    def active_target(self) -> ScanTarget | None:
        """Return the live scan target for the active document, if any."""
        doc = self._port.get_active_document()
        return self._live_target(doc) if doc is not None else None

    # -- live documents ------------------------------------------------------

    def _open_documents(self) -> list[object]:
        lister = getattr(self._port, "list_open_documents", None)
        if not callable(lister):
            return []
        docs = lister()
        if not isinstance(docs, (list, tuple)):
            return []
        return [doc for doc in docs if doc is not None]

    def _live_target(self, doc: object) -> ScanTarget:
        doc_id = str(getattr(doc, "Name", ""))
        label = str(getattr(doc, "Label", "") or doc_id)
        varsets: list[ScanVarSet] = []
        sheets: list[ScanSheet] = []
        entries: list[ExpressionEntry] = []

        for obj in _iter_objects(doc):
            type_id = getattr(obj, "TypeId", None)
            name = str(getattr(obj, "Name", "") or "")
            if not name:
                continue
            obj_label = str(getattr(obj, "Label", "") or name)
            if type_id == VARSET_TYPE_ID:
                varsets.append(
                    ScanVarSet(name=name, label=obj_label, variables=_live_variables(obj))
                )
            elif type_id == SHEET_TYPE_ID:
                sheet_entries = _live_sheet_cells(doc_id, obj, obj_label)
                sheets.append(
                    ScanSheet(name=name, label=obj_label, aliases=dict(_live_aliases(obj)))
                )
                entries.extend(sheet_entries)
            entries.extend(_live_expressions(doc_id, obj, obj_label))

        return ScanTarget(
            doc_id=doc_id,
            label=label,
            is_open=True,
            file_path=_norm_path(_document_file_name(doc)),
            varsets=tuple(varsets),
            sheets=tuple(sheets),
            entries=tuple(entries),
            document=doc,
        )

    # -- closed files ---------------------------------------------------------

    def _file_target(self, path: str) -> ScanTarget | None:
        """Parse (or reuse) a closed file; returns None on read errors."""
        abs_path = os.path.abspath(path)
        signature = _file_signature(abs_path)
        cached = self._file_cache.get(abs_path)
        parsed: FcstdDocument | None
        if cached is not None and cached[:2] == signature:
            parsed = cached[2]
        else:
            try:
                parsed = read_fcstd(abs_path)
            except FcstdReadError:
                parsed = None
            self._file_cache[abs_path] = (*signature, parsed)
        if parsed is None:
            return None
        return _file_scan_target(parsed)


def _file_scan_target(fcstd: FcstdDocument) -> ScanTarget:
    return ScanTarget(
        doc_id=fcstd.doc_name,
        label=fcstd.label,
        is_open=False,
        file_path=fcstd.path,
        varsets=tuple(
            ScanVarSet(name=v.name, label=v.label, variables=dict(v.variables))
            for v in fcstd.varsets
        ),
        sheets=tuple(
            ScanSheet(name=s.name, label=s.label, aliases=dict(s.aliases))
            for s in fcstd.sheets
        ),
        entries=fcstd.entries,
    )


# -- small helpers ------------------------------------------------------------


def _is_temporary(doc: object) -> bool:
    return bool(getattr(doc, "Temporary", False))


def _document_file_name(doc: object) -> str:
    getter = getattr(doc, "FileName", None)
    if isinstance(getter, str):
        return getter
    return ""


def _norm_path(path: str | None) -> str:
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(path))


def _file_signature(path: str) -> tuple[float, int]:
    try:
        stat = os.stat(path)
    except OSError:
        return (0.0, 0)
    return (stat.st_mtime, stat.st_size)


def _iter_objects(doc: object) -> Iterator[object]:
    for obj in getattr(doc, "Objects", []) or []:
        if obj is not None:
            yield obj


def _live_variables(obj: object) -> dict[str, str]:
    variables: dict[str, str] = {}
    for prop in getattr(obj, "PropertiesList", []) or []:
        if is_excluded_varset_property(prop):
            continue
        variables[str(prop)] = _group_of_property(obj, str(prop))
    return variables


def _group_of_property(obj: object, prop: str) -> str:
    getter = getattr(obj, VARSET_GROUP_GETTER_ATTR, None)
    if not callable(getter):
        return "Base"
    try:
        group = str(getter(prop) or "").strip()
    except Exception:  # pylint: disable=broad-exception-caught
        return "Base"
    return group or "Base"


def _live_aliases(sheet: object) -> dict[str, str]:
    """Return alias->cell mapping using every API the host version provides."""
    for getter in (
        _alias_map_from_getAliases,
        _alias_map_from_properties,
        _scan_aliases_via_cell_from_alias,
        _scan_aliases_via_getAlias,
    ):
        aliases = getter(sheet)
        if aliases:
            return aliases
    return {}


def _coerce_mapping(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {str(k): str(v) for k, v in value.items()}
    return {}


def _normalize_alias_map(raw: dict[str, str]) -> dict[str, str]:
    """Invert a cell->alias mapping into alias->cell when needed."""
    if not raw:
        return {}
    key_cells = _count_cell_like(list(raw.keys()))
    val_cells = _count_cell_like(list(raw.values()))
    if key_cells > val_cells:
        return {alias: cell for cell, alias in raw.items()}
    return raw


def _count_cell_like(values: object) -> int:
    if not isinstance(values, (list, tuple, set)):
        return 0
    return sum(1 for v in values if _CELL_RE.match(str(v or "")))


def _alias_map_from_getAliases(spreadsheet: object) -> dict[str, str]:
    getter = getattr(spreadsheet, "getAliases", None)
    if not callable(getter):
        return {}
    try:
        raw = getter()
    except Exception:  # pylint: disable=broad-exception-caught
        return {}
    return _normalize_alias_map(_coerce_mapping(raw))


def _alias_map_from_properties(spreadsheet: object) -> dict[str, str]:
    for prop_name in ("Alias", "Aliases"):
        normalized = _normalize_alias_map(_coerce_mapping(getattr(spreadsheet, prop_name, None)))
        if normalized:
            return normalized
    return {}


def _iter_cell_coordinates(*, max_rows: int, max_cols: int) -> Iterator[str]:
    cols = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for col_idx in range(max_cols):
        a = cols[col_idx % 26]
        prefix = a if col_idx < 26 else f"{cols[(col_idx // 26) - 1]}{a}"
        for row in range(1, max_rows + 1):
            yield f"{prefix}{row}"


def _candidate_cell_addresses(spreadsheet: object) -> Iterator[str]:
    cells = _live_used_cells(spreadsheet)
    if cells is not None:
        yield from cells
        return
    yield from _iter_cell_coordinates(max_rows=200, max_cols=52)


def _iter_cell_aliases(spreadsheet: object) -> Iterator[tuple[str, str]]:
    getter_one = getattr(spreadsheet, "getAlias", None)
    if not callable(getter_one):
        return
    for cell in _candidate_cell_addresses(spreadsheet):
        try:
            alias = getter_one(cell)
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        if alias:
            yield str(cell), str(alias)


def _scan_aliases_via_getAlias(spreadsheet: object) -> dict[str, str]:
    return {alias: cell for cell, alias in _iter_cell_aliases(spreadsheet)}


def _scan_aliases_via_cell_from_alias(spreadsheet: object) -> dict[str, str]:
    resolved_getter = getattr(spreadsheet, "getCellFromAlias", None)
    aliases: dict[str, str] = {}
    for cell, alias in _iter_cell_aliases(spreadsheet):
        resolved = cell
        if callable(resolved_getter):
            try:
                value = resolved_getter(alias)
            except Exception:  # pylint: disable=broad-exception-caught
                value = None
            if value:
                resolved = str(value)
        aliases[alias] = resolved
    return aliases


def _live_cell_texts(sheet: object) -> Iterator[tuple[str, str]]:
    """Yield `(address, content)` for non-empty cells of a live sheet."""
    for cell in _candidate_cell_addresses(sheet):
        text = _try_get_cell_text(sheet, cell)
        if text:
            yield str(cell), text


def _try_get_cell_text(sheet: object, cell: str) -> str | None:
    for getter_name in ("getContents", "get"):
        getter = getattr(sheet, getter_name, None)
        if not callable(getter):
            continue
        try:
            value = getter(cell)
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        if isinstance(value, str):
            return value
        if value is not None:
            return str(value)
    return None


def _live_used_cells(sheet: object) -> list[str] | None:
    for attr in SHEET_CELLS_ATTRS:
        getter = getattr(sheet, attr, None)
        if not callable(getter):
            continue
        try:
            cells = getter()
        except Exception:  # pylint: disable=broad-exception-caught
            continue
        if isinstance(cells, (list, tuple)):
            return [str(cell) for cell in cells if cell]
    return None


def _live_sheet_cells(doc_id: str, sheet: object, label: str) -> list[ExpressionEntry]:
    name = str(getattr(sheet, "Name", ""))
    return [
        ExpressionEntry(
            source_doc=doc_id,
            kind=ENTRY_KIND_CELL,
            object_name=name,
            lhs=address,
            rhs=text,
            object_label=label,
        )
        for address, text in _live_cell_texts(sheet)
    ]


def _live_expressions(doc_id: str, obj: object, label: str) -> Iterator[ExpressionEntry]:
    expressions = getattr(obj, "ExpressionEngine", None)
    if not expressions or not isinstance(expressions, (list, tuple)):
        return
    name = str(getattr(obj, "Name", ""))
    for expr in expressions:
        if not isinstance(expr, (list, tuple)) or len(expr) < 2:
            continue
        lhs = str(expr[0])
        rhs = str(expr[1])
        if not lhs or not rhs:
            continue
        yield ExpressionEntry(
            source_doc=doc_id,
            kind=ENTRY_KIND_EXPRESSION,
            object_name=name,
            lhs=lhs,
            rhs=rhs,
            object_label=label,
        )


__all__ = [
    "DocumentScanner",
    "ScanSheet",
    "ScanTarget",
    "ScanVarSet",
]
