"""Unit tests for VarsetDataSource.

These tests mock the FreeCAD-facing query functions so they can run without FreeCAD.
"""

from __future__ import annotations

from freecad.datamanager_wb.domain.parent_child_ref import ParentChildRef
from freecad.datamanager_wb.domain.reference_hit import ReferenceHit
from freecad.datamanager_wb.varsets.varset_datasource import VarsetDataSource


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


def test_get_child_refs_for_virtual_varset_filters_by_group(monkeypatch) -> None:
    """VarsetDataSource.get_child_refs filters variables by virtual varset group selection."""
    ds = VarsetDataSource()

    def fake_groups(varset_name: str, *, ctx=None, scope=None, scanner=None):
        assert varset_name == "VS"
        return {"a": "Base", "b": "Group1"}

    monkeypatch.setattr("freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableGroups", fake_groups)
    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableNamesForGroup",
        lambda varset_name, group, *, ctx=None, scope=None, scanner=None: (
            ["x"] if group == "Group1" else ["base_only"]
        ),
    )
    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableNames",
        lambda varset_name, *, ctx=None, scope=None, scanner=None: ["x", "y"],
    )

    refs = ds.get_child_refs(["VS.Group1"])
    assert refs == [ParentChildRef(parent="VS", child="x")]


def test_get_child_refs_for_non_virtual_parent_includes_all(monkeypatch) -> None:
    """VarsetDataSource.get_child_refs returns all variables for a non-virtual varset parent."""
    ds = VarsetDataSource()

    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableGroups",
        lambda varset_name, *, ctx=None, scope=None, scanner=None: {"a": "Base", "b": "Group1"},
    )
    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableNames",
        lambda varset_name, *, ctx=None, scope=None, scanner=None: ["b", "a"],
    )

    refs = ds.get_child_refs(["VS"])
    assert refs == [ParentChildRef(parent="VS", child="a"), ParentChildRef(parent="VS", child="b")]


def test_virtual_parent_with_unknown_group_falls_back_to_normal(monkeypatch) -> None:
    """Unknown virtual group selection falls back to treating the selection as a normal variable prefix."""
    ds = VarsetDataSource()

    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableGroups",
        lambda varset_name, *, ctx=None, scope=None, scanner=None: {"a": "Base", "b": "Group1"},
    )
    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableNames",
        lambda varset_name, *, ctx=None, scope=None, scanner=None: ["x"],
    )

    refs = ds.get_child_refs(["VS.Unknown"])
    assert refs == [ParentChildRef(parent="VS", child="Unknown.x")]


def test_qualified_parents_are_supported(monkeypatch) -> None:
    """Document-qualified parent names are accepted and preserved in child refs."""
    ds = VarsetDataSource()

    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableGroups",
        lambda varset_name, *, ctx=None, scope=None, scanner=None: (
            {"h": "Base"} if varset_name == "Doc#VS" else {}
        ),
    )
    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetVariableNames",
        lambda varset_name, *, ctx=None, scope=None, scanner=None: (
            ["h"] if varset_name == "Doc#VS" else []
        ),
    )

    refs = ds.get_child_refs(["Doc#VS"])
    assert refs == [ParentChildRef(parent="Doc#VS", child="h")]


def test_expression_items_tag_only_external_hits(monkeypatch) -> None:
    """Hits from other documents carry the document; owner-document hits stay plain."""
    ds = VarsetDataSource()

    def fake_refs(varset_name, variable_name=None, *, ctx=None, scope=None, scanner=None):
        return [
            _hit("DocA", "VS.h", "<<VS>>.h"),
            _hit("DocB", "Box.Length", "DocA#VS.h", source="file", owner="DocA"),
        ]

    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetReferences", fake_refs
    )

    items, counts = ds.get_expression_items([ParentChildRef(parent="VS", child="h")])
    assert counts == {"VS.h": 2}

    external = [item for item in items if item.doc_id]
    internal = [item for item in items if not item.doc_id]
    assert [item.doc_id for item in external] == ["DocB"]
    assert external[0].doc_path is None  # file_path was None in the hit
    assert external[0].display_text.startswith("DocB.Box.Length = ")
    assert internal[0].display_text == "VS.h = <<VS>>.h"


def test_remove_unused_children_fails_for_closed_documents(monkeypatch) -> None:
    """A variable with no references but a closed home document cannot be removed."""
    from freecad.datamanager_wb.scanning.scanner import ScanTarget
    from freecad.datamanager_wb.varsets.varset_query import ScanVarSet

    ds = VarsetDataSource()

    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.getVarsetReferences",
        lambda *args, **kwargs: [],
    )
    closed_target = ScanTarget(doc_id="DocA", label="DocA", is_open=False, file_path="/tmp/a.FCStd")
    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.find_varset",
        lambda varset_name, **kwargs: (closed_target, ScanVarSet(name="VS", label="VS")),
    )
    calls: list[str] = []
    monkeypatch.setattr(
        "freecad.datamanager_wb.varsets.varset_datasource.removeVarsetVariable",
        lambda *args, **kwargs: calls.append("removed") or True,
    )

    result = ds.remove_unused_children([ParentChildRef(parent="DocA#VS", child="h")])
    assert result.removed == []
    assert result.failed == ["DocA#VS.h"]
    assert calls == []

