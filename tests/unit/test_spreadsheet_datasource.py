"""Unit tests for `SpreadsheetDataSource`."""

from __future__ import annotations

from freecad.datamanager_wb.domain.parent_child_ref import ParentChildRef
from freecad.datamanager_wb.domain.reference_hit import ReferenceHit
from freecad.datamanager_wb.scanning.scanner import ScanSheet, ScanTarget
from freecad.datamanager_wb.spreadsheets.spreadsheet_datasource import SpreadsheetDataSource


def _hit(
    doc_id: str, lhs: str, rhs: str, *, source: str = "open", owner: str | None = None
) -> ReferenceHit:
    return ReferenceHit(
        doc_id=doc_id,
        doc_label=doc_id,
        owner_doc_id=owner or doc_id,
        source=source,
        file_path=None,
        object_name=lhs.split(".", 1)[0],
        lhs=lhs,
        rhs=rhs,
    )


def _open_target() -> ScanTarget:
    return ScanTarget(
        doc_id="Doc",
        label="Doc",
        is_open=True,
        file_path="/tmp/doc.FCStd",
        document=object(),
    )


def _sheet() -> ScanSheet:
    return ScanSheet(name="Sheet", label="Sheet")


def test_get_child_refs_sorts(monkeypatch) -> None:
    """SpreadsheetDataSource.get_child_refs returns sorted alias refs."""
    ds = SpreadsheetDataSource()

    monkeypatch.setattr(
        "freecad.datamanager_wb.spreadsheets.spreadsheet_datasource.getSpreadsheetAliasNames",
        lambda sheet_name, *, ctx=None, scope=None, scanner=None: ["b", "a"],
    )

    refs = ds.get_child_refs(["Sheet"])
    assert refs == [ParentChildRef(parent="Sheet", child="a"), ParentChildRef(parent="Sheet", child="b")]


def test_get_expression_items_counts_and_operator(monkeypatch) -> None:
    """SpreadsheetDataSource.get_expression_items returns reference counts and operators."""
    ds = SpreadsheetDataSource()

    def fake_refs(
        sheet_name: str, alias_name: str | None = None, *, ctx=None, scope=None, scanner=None
    ):
        assert sheet_name == "Sheet"
        assert alias_name == "foo"
        return [
            _hit("Doc", "Sheet.A1", "'foo"),
            _hit("Doc", "Box.Length", "=foo+1"),
        ]

    monkeypatch.setattr(
        "freecad.datamanager_wb.spreadsheets.spreadsheet_datasource.getSpreadsheetAliasReferences",
        fake_refs,
    )

    items, counts = ds.get_expression_items([ParentChildRef(parent="Sheet", child="foo")])
    assert counts == {"Sheet.foo": 2}

    by_lhs = {item.lhs: item for item in items}
    assert by_lhs["Sheet.A1"].operator == ":="
    assert by_lhs["Box.Length"].operator == "="
    assert all(item.doc_id is None for item in items)  # active-document scope hides doc tags


def test_external_hits_are_document_qualified(monkeypatch) -> None:
    """Only hits from outside the owner document carry a document qualifier."""
    ds = SpreadsheetDataSource()

    def fake_refs(
        sheet_name: str, alias_name: str | None = None, *, ctx=None, scope=None, scanner=None
    ):
        return [
            _hit("DocA", "Sheet.A1", "'foo"),
            _hit("DocB", "Box.Length", "=DocA#Sheet.foo", source="file", owner="DocA"),
        ]

    monkeypatch.setattr(
        "freecad.datamanager_wb.spreadsheets.spreadsheet_datasource.getSpreadsheetAliasReferences",
        fake_refs,
    )

    items, _counts = ds.get_expression_items([ParentChildRef(parent="Sheet", child="foo")])
    external = [item for item in items if item.doc_id]
    internal = [item for item in items if not item.doc_id]
    assert [item.doc_id for item in external] == ["DocB"]
    assert external[0].display_text.startswith("DocB.Box.Length = ")
    assert internal[0].display_text.startswith("Sheet.A1 := ")


def test_remove_unused_children(monkeypatch) -> None:
    """SpreadsheetDataSource.remove_unused_children removes only aliases with zero references."""
    ds = SpreadsheetDataSource()

    def fake_refs(
        sheet_name: str, alias_name: str | None = None, *, ctx=None, scope=None, scanner=None
    ):
        if alias_name == "used":
            return [_hit("Doc", "Box.Length", "=used+1")]
        return []

    monkeypatch.setattr(
        "freecad.datamanager_wb.spreadsheets.spreadsheet_datasource.getSpreadsheetAliasReferences",
        fake_refs,
    )
    monkeypatch.setattr(
        "freecad.datamanager_wb.spreadsheets.spreadsheet_datasource.find_sheet",
        lambda sheet_name, **kwargs: (_open_target(), _sheet()),
    )
    monkeypatch.setattr(
        "freecad.datamanager_wb.spreadsheets.spreadsheet_datasource.removeSpreadsheetAlias",
        lambda sheet_name, alias_name, *, ctx=None, doc=None: True,
    )

    result = ds.remove_unused_children(
        [ParentChildRef(parent="Sheet", child="unused"), ParentChildRef(parent="Sheet", child="used")]
    )
    assert result.removed == ["Sheet.unused"]
    assert result.still_used == ["Sheet.used"]
    assert result.failed == []


def test_remove_unused_children_fails_for_closed_documents(monkeypatch) -> None:
    """Aliases inside closed (scanned) documents cannot be removed and are reported failed."""
    ds = SpreadsheetDataSource()

    monkeypatch.setattr(
        "freecad.datamanager_wb.spreadsheets.spreadsheet_datasource.getSpreadsheetAliasReferences",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "freecad.datamanager_wb.spreadsheets.spreadsheet_datasource.find_sheet",
        lambda sheet_name, **kwargs: (
            ScanTarget(doc_id="Doc", label="Doc", is_open=False, file_path="/tmp/doc.FCStd"),
            ScanSheet(name="Sheet", label="Sheet"),
        ),
    )

    result = ds.remove_unused_children([ParentChildRef(parent="Sheet", child="unused")])
    assert result.removed == []
    assert result.failed == ["Sheet.unused"]
