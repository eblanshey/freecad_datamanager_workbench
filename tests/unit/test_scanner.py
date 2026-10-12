"""Unit tests for the document scanner (live documents + closed files)."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

from freecad.datamanager_wb.scanning.scanner import DocumentScanner
from freecad.datamanager_wb.scanning.scope import DocumentScope
from fakes import FakeDocument, FakeObject, FakePort, FakeSheet, FakeVarSet


def _write_fcstd(path: Path, document_xml: str) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", document_xml)
    return path


_MINIMAL_XML = (
    '<?xml version="1.0"?><Document>'
    '<Properties><Property name="Label" type="App::PropertyString">'
    '<String value="ClosedDoc"/></Property></Properties>'
    "<Objects><Object type=\"App::VarSet\" name=\"VS\"/></Objects>"
    "<ObjectData><Object name=\"VS\"><Properties>"
    '<Property name="Label" type="App::PropertyString"><String value="Vars"/></Property>'
    '<Property name="h" type="App::PropertyDistance" group="Base"/>'
    "</Properties></Object></ObjectData></Document>"
)


def test_resolve_includes_all_open_documents() -> None:
    doc_a = FakeDocument("DocA", objects=[FakeVarSet("VS", variables={"h": "Base"})])
    doc_b = FakeDocument("DocB", objects=[])
    temp = FakeDocument("Temp", objects=[], temporary=True)
    port = FakePort(active=doc_a, open_docs=[doc_a, doc_b, temp])
    scanner = DocumentScanner(port)

    targets = scanner.resolve(DocumentScope.empty())
    assert {t.doc_id for t in targets} == {"DocA", "DocB"}
    assert targets[0].is_open
    assert targets[0].varsets[0].variables == {"h": "Base"}


def test_active_target_returns_only_active_document() -> None:
    doc_a = FakeDocument("DocA", objects=[])
    doc_b = FakeDocument("DocB", objects=[])
    port = FakePort(active=doc_a, open_docs=[doc_a, doc_b])
    scanner = DocumentScanner(port)

    target = scanner.active_target()
    assert target is not None
    assert target.doc_id == "DocA"
    assert FakeDocument("DocB") != target.document


def test_extra_file_scanned_without_opening(tmp_path: Path) -> None:
    fcstd = _write_fcstd(tmp_path / "Model.FCStd", _MINIMAL_XML)
    port = FakePort(active=None, open_docs=[])
    scanner = DocumentScanner(port)

    targets = scanner.resolve(DocumentScope(extra_files=(str(fcstd),)))
    assert len(targets) == 1
    target = targets[0]
    assert target.doc_id == "Model"
    assert target.label == "ClosedDoc"
    assert not target.is_open
    assert target.file_path == os.path.abspath(str(fcstd))
    assert target.varsets[0].name == "VS"
    assert target.varsets[0].label == "Vars"


def test_unreadable_extra_files_are_skipped(tmp_path: Path) -> None:
    port = FakePort(active=None, open_docs=[])
    scanner = DocumentScanner(port)
    scope = DocumentScope(extra_files=(str(tmp_path / "gone.FCStd"),))
    assert scanner.resolve(scope) == []


def _variant_fcstd(path: Path, doc_label: str, varset_name: str) -> Path:
    xml = _MINIMAL_XML.replace("ClosedDoc", doc_label).replace('name="VS"', f'name="{varset_name}"')
    return _write_fcstd(path, xml)


def test_saved_active_document_pulls_in_its_folder_tree(tmp_path: Path) -> None:
    """fcxref-style: the saved active document's directory is searched recursively."""
    own = _variant_fcstd(tmp_path / "Drive.FCStd", "Drive", "VS")
    _variant_fcstd(tmp_path / "Sibling.FCStd", "Sibling", "Sib")
    sub = tmp_path / "sub"
    sub.mkdir()
    _variant_fcstd(sub / "Child.FCStd", "Child", "Kid")
    hidden = tmp_path / ".git"
    hidden.mkdir()
    _variant_fcstd(hidden / "Stale.FCStd", "Stale", "Old")

    live = FakeDocument("Drive", objects=[], file_name=str(own))
    port = FakePort(active=live, open_docs=[live])
    scanner = DocumentScanner(port)

    targets = scanner.resolve(DocumentScope.empty())
    by_id = {t.doc_id: t for t in targets}
    assert set(by_id) == {"Drive", "Sibling", "Child"}
    assert by_id["Drive"].is_open  # the active file itself stays a live scan
    assert not by_id["Sibling"].is_open
    assert not by_id["Child"].is_open


def test_unsaved_active_document_contributes_no_folder(tmp_path: Path) -> None:
    fcstd = _write_fcstd(tmp_path / "Model.FCStd", _MINIMAL_XML)
    unsaved = FakeDocument("Untitled", objects=[])  # FileName == ""
    port = FakePort(active=unsaved, open_docs=[unsaved])
    scanner = DocumentScanner(port)

    targets = scanner.resolve(DocumentScope(extra_files=(str(fcstd),)))
    assert [t.doc_id for t in targets] == ["Untitled", "Model"]


def test_folder_glob_deduplicates_against_open_documents(tmp_path: Path) -> None:
    first = _variant_fcstd(tmp_path / "A.FCStd", "DocA", "VA")
    _variant_fcstd(tmp_path / "B.FCStd", "DocB", "VB")
    doc_a = FakeDocument("A", objects=[], file_name=str(first))
    doc_b = FakeDocument("B", objects=[], file_name=str(tmp_path / "B.FCStd"))
    port = FakePort(active=doc_a, open_docs=[doc_a, doc_b])
    scanner = DocumentScanner(port)

    targets = scanner.resolve(DocumentScope.empty())
    assert len(targets) == 2
    assert all(t.is_open for t in targets)  # both live docs win over their files


def test_extra_file_deduplicates_to_live_document(tmp_path: Path) -> None:
    fcstd = _write_fcstd(tmp_path / "Model.FCStd", _MINIMAL_XML)
    live = FakeDocument("Model", objects=[], file_name=str(fcstd))
    port = FakePort(active=live, open_docs=[live])
    scanner = DocumentScanner(port)

    targets = scanner.resolve(DocumentScope(extra_files=(str(fcstd),)))
    assert len(targets) == 1
    assert targets[0].is_open  # live document wins over the on-disk copy


def test_file_cache_invalidates_on_change(tmp_path: Path) -> None:
    path = _write_fcstd(tmp_path / "Model.FCStd", _MINIMAL_XML)
    port = FakePort(active=None, open_docs=[])
    scanner = DocumentScanner(port)
    scope = DocumentScope(extra_files=(str(path),))

    first = scanner.resolve(scope)
    assert first[0].varsets[0].name == "VS"

    updated = _MINIMAL_XML.replace('name="VS"', 'name="Vars2"')
    os.utime(path, (0, 0))  # force mtime change
    _write_fcstd(path, updated)
    os.utime(path, None)

    second = scanner.resolve(scope)
    assert second[0].varsets[0].name == "Vars2"


def test_repeated_extra_files_are_deduplicated(tmp_path: Path) -> None:
    fcstd = _write_fcstd(tmp_path / "Model.FCStd", _MINIMAL_XML)
    port = FakePort(active=None, open_docs=[])
    scanner = DocumentScanner(port)
    scope = DocumentScope(extra_files=(str(fcstd), str(fcstd)))
    assert len(scanner.resolve(scope)) == 1


def test_live_sheet_alias_and_cell_entries() -> None:
    sheet = FakeSheet(
        "Table",
        aliases={"width": "B2"},
        cells={"A1": "5", "B2": "width", "C3": "=Params.width"},
    )
    doc = FakeDocument("DocA", objects=[sheet])
    port = FakePort(active=doc, open_docs=[doc])
    scanner = DocumentScanner(port)

    target = scanner.active_target()
    assert target is not None
    assert target.sheets[0].aliases == {"width": "B2"}
    cells = {(e.lhs, e.rhs) for e in target.entries if e.kind == "cell"}
    assert cells == {("A1", "5"), ("B2", "width"), ("C3", "=Params.width")}
    assert all(e.object_name == "Table" for e in target.entries)


def test_live_expression_engine_entries_captured() -> None:
    obj = FakeObject("Box", [("Length", "Params.width * 2")])
    doc = FakeDocument("DocA", objects=[obj])
    port = FakePort(active=doc, open_docs=[doc])
    scanner = DocumentScanner(port)

    target = scanner.active_target()
    assert target is not None
    exprs = {(e.lhs, e.rhs) for e in target.entries if e.kind == "expression"}
    assert exprs == {("Length", "Params.width * 2")}
    assert target.entries[0].binding_key() == "Box.Length"
