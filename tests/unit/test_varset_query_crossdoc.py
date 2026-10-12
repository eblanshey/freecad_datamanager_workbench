"""Cross-document behavior of the VarSet query helpers."""

from __future__ import annotations

import zipfile
from pathlib import Path

from freecad.datamanager_wb.scanning.scope import DocumentScope
from freecad.datamanager_wb.varsets import varset_query
from fakes import FakeDocument, FakeObject, FakePort, FakeVarSet

_MODEL_XML = (
    '<?xml version="1.0"?><Document>'
    '<Properties><Property name="Label"><String value="Motor"/></Property></Properties>'
    "<Objects>"
    "<Object type=\"App::VarSet\" name=\"Params\"/>"
    "<Object type=\"Part::Box\" name=\"Box\"/>"
    "</Objects>"
    "<ObjectData>"
    '<Object name="Params"><Properties>'
    '<Property name="Label"><String value="Motor Params"/></Property>'
    '<Property name="kv" type="App::PropertyFloat" group="Base"/>'
    "</Properties></Object>"
    '<Object name="Box"><Properties>'
    '<Property name="ExpressionEngine" type="App::PropertyExpressionEngine">'
    '<ExpressionEngine count="1">'
    '<Expression path="Length" expression="Params.kv * 2"/>'
    "</ExpressionEngine></Property>"
    "</Properties></Object>"
    "</ObjectData></Document>"
)


def _closed_model(tmp_path: Path) -> Path:
    path = tmp_path / "Model.FCStd"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", _MODEL_XML)
    return path


def _port_with_two_docs() -> FakePort:
    owner = FakeDocument(
        "Drive",
        objects=[FakeVarSet("Params", label="Parameters", variables={"height": "Base"})],
    )
    referencer = FakeDocument(
        "Other",
        objects=[FakeObject("Box", [("Length", "Drive#Params.height + 1")])],
    )
    return FakePort(active=owner, open_docs=[owner, referencer])


def test_varsets_listed_from_active_document_only(monkeypatch) -> None:
    """Other documents contribute references, never parent/child entries."""
    owner = FakeDocument("Drive", objects=[FakeVarSet("Params", variables={"height": "Base"})])
    other = FakeDocument("Other", objects=[FakeVarSet("Params", variables={"width": "Base"})])
    port = FakePort(active=owner, open_docs=[owner, other])
    monkeypatch.setattr(varset_query, "get_port", lambda _ctx=None: port)

    assert list(varset_query.getVarsets()) == ["Params"]


def test_references_searched_in_every_open_document(monkeypatch) -> None:
    port = _port_with_two_docs()
    monkeypatch.setattr(varset_query, "get_port", lambda _ctx=None: port)

    hits = varset_query.getVarsetReferences("Params", "height")
    external = [hit for hit in hits if hit.is_external]
    assert ("Other", "Box.Length") in {(hit.doc_id, hit.lhs) for hit in external}
    assert all(hit.source == "open" for hit in external)
    assert all(hit.owner_doc_id == "Drive" for hit in hits)


def test_references_found_in_closed_file(tmp_path: Path, monkeypatch) -> None:
    model = _closed_model(tmp_path)
    port = FakePort(active=None, open_docs=[])
    monkeypatch.setattr(varset_query, "get_port", lambda _ctx=None: port)

    scope = DocumentScope(extra_files=(str(model),))
    hits = varset_query.getVarsetReferences("Model#Params", "kv", scope=scope)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.doc_id == "Model"
    assert hit.doc_label == "Motor"
    assert hit.source == "file"
    assert not hit.is_external  # reference lives inside the owner document
    assert hit.lhs == "Box.Length"
    assert hit.file_path is not None and hit.file_path.endswith("Model.FCStd")


def test_open_document_reference_to_closed_document(tmp_path: Path, monkeypatch) -> None:
    model = _closed_model(tmp_path)
    live = FakeDocument(
        "Drive",
        objects=[FakeObject("Box", [("Length", "Model#Params.kv")])],
    )
    port = FakePort(active=live, open_docs=[live])
    monkeypatch.setattr(varset_query, "get_port", lambda _ctx=None: port)

    scope = DocumentScope(extra_files=(str(model),))
    hits = varset_query.getVarsetReferences("Model#Params", "kv", scope=scope)
    docs = {hit.doc_id for hit in hits}
    assert docs == {"Model", "Drive"}
    assert hits[0].doc_id == "Model"  # owner document first
    by_doc = {hit.doc_id: hit for hit in hits}
    assert by_doc["Drive"].source == "open" and by_doc["Drive"].is_external
    assert by_doc["Model"].source == "file" and not by_doc["Model"].is_external


def test_variable_groups_read_from_closed_file(tmp_path: Path, monkeypatch) -> None:
    model = _closed_model(tmp_path)
    port = FakePort(active=None, open_docs=[])
    monkeypatch.setattr(varset_query, "get_port", lambda _ctx=None: port)

    scope = DocumentScope(extra_files=(str(model),))
    groups = varset_query.getVarsetVariableGroups("Model#Params", scope=scope)
    assert groups == {"kv": "Base"}


def test_references_dedupe_across_entries(monkeypatch) -> None:
    """The same (doc, binding, expression) triple is reported only once."""
    doc = FakeDocument(
        "Drive",
        objects=[
            FakeVarSet("Params", variables={"height": "Base"}),
            FakeObject("Box", [("Length", "Params.height")]),
            FakeObject("Box", [("Length", "Params.height")]),
        ],
    )
    port = FakePort(active=doc, open_docs=[doc])
    monkeypatch.setattr(varset_query, "get_port", lambda _ctx=None: port)

    hits = varset_query.getVarsetReferences("Params", "height")
    assert len(hits) == 1
