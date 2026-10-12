"""PanelController: reference-file scope ownership and qualified labels."""

from __future__ import annotations

import zipfile
from pathlib import Path

from freecad.datamanager_wb.ports.freecad_context import FreeCadContext
from freecad.datamanager_wb.scanning.scope import DocumentScope
from freecad.datamanager_wb.ui.panel_controller import PanelController
from fakes import FakeApp, FakeDocument, FakeVarSet


def _controller(app: FakeApp) -> PanelController:
    return PanelController(ctx=FreeCadContext(app=app))  # type: ignore[arg-type]


def test_default_scope_has_no_extra_files() -> None:
    controller = _controller(FakeApp())
    assert controller.get_scope().extra_files == ()


def test_set_scope_updates_get_scope() -> None:
    controller = _controller(FakeApp())
    controller.set_scope(DocumentScope(extra_files=("/x/a.FCStd",)))
    assert controller.get_scope().extra_files == ("/x/a.FCStd",)


def test_list_open_document_names_filters_temporary() -> None:
    doc_a = FakeDocument("A")
    temp = FakeDocument("T", temporary=True)
    controller = _controller(FakeApp(active=doc_a, docs=[doc_a, temp]))
    assert controller.list_open_document_names() == ["A"]


def test_qualified_label_from_open_document() -> None:
    doc = FakeDocument("Drive", objects=[FakeVarSet("Params", label="Parameters")])
    controller = _controller(FakeApp(docs=[doc]))
    assert controller.get_object_label("Drive#Params") == "Drive#Parameters"


def test_qualified_label_falls_back_to_scanned_label(tmp_path: Path) -> None:
    path = tmp_path / "Model.FCStd"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Document.xml",
            '<?xml version="1.0"?><Document>'
            "<Objects><Object type=\"App::VarSet\" name=\"Params\"/></Objects>"
            "<ObjectData><Object name=\"Params\"><Properties>"
            '<Property name="Label"><String value="Motor Params"/></Property>'
            "</Properties></Object></ObjectData></Document>",
        )
    controller = _controller(FakeApp())
    controller.set_scope(DocumentScope(extra_files=(str(path),)))
    assert controller.get_object_label("Model#Params") == "Model#Motor Params"


def test_label_for_plain_name_uses_active_document() -> None:
    doc = FakeDocument("Active", objects=[FakeVarSet("Params", label="Live Params")])
    controller = _controller(FakeApp(active=doc, docs=[doc]))
    assert controller.get_object_label("Params") == "Live Params"
