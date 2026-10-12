# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Static reader for closed ``.FCStd`` documents.

A ``.FCStd`` file is a zip archive; ``Document.xml`` inside it holds the full
document object model as saved:

- ``<Objects>``: the object index (name/type mapping),
- ``<ObjectData>``: per-object properties, including
  ``<Property name="ExpressionEngine">`` bindings and spreadsheet
  ``<Property name="cells">`` contents with the ``alias`` attribute,
- document ``<Properties>``: including the document ``Label``.

This module parses those structures with the standard library only, so closed
documents can be scanned for references without opening them in FreeCAD.
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from xml.etree import ElementTree

from ..domain.expression_entry import ENTRY_KIND_CELL, ENTRY_KIND_EXPRESSION, ExpressionEntry
from ..domain.qualified_parent import document_id_from_path
from ..domain.varset_builtin_properties import is_excluded_varset_property

VARSET_TYPE_ID = "App::VarSet"
SHEET_TYPE_ID = "Spreadsheet::Sheet"


class FcstdReadError(Exception):
    """Raised when a ``.FCStd`` file cannot be read or parsed."""


@dataclass(frozen=True)
class FcstdVarSet:
    """A VarSet found in a closed document.

    Attributes:
        name: Object internal name.
        label: Object label.
        variables: Mapping of variable name -> property group.
    """

    name: str
    label: str
    variables: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FcstdSheet:
    """A spreadsheet found in a closed document.

    Attributes:
        name: Object internal name.
        label: Object label.
        aliases: Mapping of alias name -> cell address.
    """

    name: str
    label: str
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FcstdDocument:
    """Parsed contents of a closed ``.FCStd`` file.

    Attributes:
        path: Absolute file path of the archive.
        doc_name: Document name FreeCAD would use when restoring the file.
        label: Document label as saved in the file.
        varsets: All VarSets in the file.
        sheets: All spreadsheets in the file.
        entries: Expression engine bindings and non-empty cell contents.
    """

    path: str
    doc_name: str
    label: str
    varsets: tuple[FcstdVarSet, ...] = ()
    sheets: tuple[FcstdSheet, ...] = ()
    entries: tuple[ExpressionEntry, ...] = ()


def read_fcstd(path: str) -> FcstdDocument:
    """Parse a closed ``.FCStd`` file into an :class:`FcstdDocument`.

    Raises:
        FcstdReadError: When the archive cannot be opened or `Document.xml` is
            missing/unparsable.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            raw = archive.read("Document.xml")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise FcstdReadError(f"Cannot read Document.xml from {path}: {exc}") from exc

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise FcstdReadError(f"Cannot parse Document.xml in {path}: {exc}") from exc

    abs_path = os.path.abspath(path)
    doc_name = document_id_from_path(path)
    label = _document_label(root) or doc_name

    types_by_name = _object_types(root)
    varsets: list[FcstdVarSet] = []
    sheets: list[FcstdSheet] = []
    entries: list[ExpressionEntry] = []

    for obj in _iter_object_data(root):
        name = str(obj.attrib.get("name") or "")
        if not name:
            continue
        type_id = obj.attrib.get("type") or types_by_name.get(name, "")
        props = _property_elements(obj)
        obj_label = _property_string(props, "Label") or name

        if type_id == VARSET_TYPE_ID:
            varsets.append(
                FcstdVarSet(name=name, label=obj_label, variables=_varset_variables(props))
            )
        elif type_id == SHEET_TYPE_ID:
            sheet_obj = _parse_sheet(props, name, obj_label, doc_name)
            if sheet_obj is not None:
                sheets.append(sheet_obj[0])
                entries.extend(sheet_obj[1])

        for expression in _iter_expressions(props):
            path_attr, expression_attr = expression
            entries.append(
                ExpressionEntry(
                    source_doc=doc_name,
                    kind=ENTRY_KIND_EXPRESSION,
                    object_name=name,
                    lhs=path_attr,
                    rhs=expression_attr,
                    object_label=obj_label,
                )
            )

    return FcstdDocument(
        path=abs_path,
        doc_name=doc_name,
        label=label,
        varsets=tuple(varsets),
        sheets=tuple(sheets),
        entries=tuple(entries),
    )


def _document_label(root: ElementTree.Element) -> str:
    props = root.find("Properties")
    if props is None:
        return ""
    return _property_string(list(props), "Label")


def _property_string(props: Iterator[ElementTree.Element] | list[ElementTree.Element], name: str) -> str:
    for prop in props:
        if prop.tag != "Property" or prop.attrib.get("name") != name:
            continue
        string_el = prop.find("String")
        if string_el is not None:
            return str(string_el.attrib.get("value") or "")
    return ""


def _object_types(root: ElementTree.Element) -> dict[str, str]:
    types: dict[str, str] = {}
    objects = root.find("Objects")
    if objects is None:
        return types
    for obj in objects.findall("Object"):
        name = obj.attrib.get("name")
        type_id = obj.attrib.get("type")
        if isinstance(name, str) and isinstance(type_id, str):
            types[name] = type_id
    return types


def _iter_object_data(root: ElementTree.Element) -> Iterator[ElementTree.Element]:
    data = root.find("ObjectData")
    if data is None:
        return
    for obj in data.findall("Object"):
        yield obj


def _property_elements(obj: ElementTree.Element) -> list[ElementTree.Element]:
    props = obj.find("Properties")
    if props is None:
        return []
    return list(props)


def _varset_variables(props: list[ElementTree.Element]) -> dict[str, str]:
    variables: dict[str, str] = {}
    for prop in props:
        if prop.tag != "Property":
            continue
        name = str(prop.attrib.get("name") or "")
        if not name or is_excluded_varset_property(name):
            continue
        variables[name] = str(prop.attrib.get("group") or "Base")
    return variables


def _parse_sheet(
    props: list[ElementTree.Element], name: str, label: str, doc_name: str
) -> tuple[FcstdSheet, list[ExpressionEntry]] | None:
    aliases: dict[str, str] = {}
    entries: list[ExpressionEntry] = []
    for prop in props:
        if prop.tag != "Property" or prop.attrib.get("name") != "cells":
            continue
        cells = prop.find("Cells")
        if cells is None:
            continue
        for cell in cells.findall("Cell"):
            address = str(cell.attrib.get("address") or "")
            if not address:
                continue
            alias = str(cell.attrib.get("alias") or "")
            if alias:
                aliases[alias] = address
            content = str(cell.attrib.get("content") or "")
            if content:
                entries.append(
                    ExpressionEntry(
                        source_doc=doc_name,
                        kind=ENTRY_KIND_CELL,
                        object_name=name,
                        lhs=address,
                        rhs=content,
                        object_label=label,
                    )
                )
    return FcstdSheet(name=name, label=label, aliases=aliases), entries


def _iter_expressions(props: list[ElementTree.Element]) -> Iterator[tuple[str, str]]:
    for prop in props:
        if prop.tag != "Property" or prop.attrib.get("name") != "ExpressionEngine":
            continue
        engine = prop.find("ExpressionEngine")
        if engine is None:
            continue
        for expression in engine.findall("Expression"):
            path = str(expression.attrib.get("path") or "")
            text = str(expression.attrib.get("expression") or "")
            if path and text:
                yield path, text
