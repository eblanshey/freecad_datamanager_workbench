"""Unit tests for document-aware selection jumps."""

from __future__ import annotations

from freecad.datamanager_wb.domain.expression_item import ExpressionItem
from freecad.datamanager_wb.ui import gui_selection


class _RecordingPort:
    def __init__(
        self,
        *,
        active: object | None,
        open_docs: dict[str, object],
        opened_files: dict[str, object] | None = None,
    ) -> None:
        self.active = active
        self.open_docs = open_docs
        self.opened_files = opened_files or {}
        self.selection: list[tuple[str, str]] = []
        self.cleared = 0
        self.activated: list[str] = []
        self.opened: list[str] = []
        self.warnings: list[str] = []

    def get_active_document(self):
        return self.active

    def get_open_document(self, doc_name: str):
        return self.open_docs.get(doc_name)

    def open_document_file(self, path: str):
        self.opened.append(path)
        return self.opened_files.get(path)

    def try_set_active_document(self, doc_name: str) -> None:
        self.activated.append(doc_name)

    def clear_selection(self) -> None:
        self.cleared += 1

    def add_selection(self, *, doc_name: str, obj_name: str) -> None:
        self.selection.append((doc_name, obj_name))

    def get_object(self, doc, name):  # noqa: ANN001
        if getattr(doc, "Name", None) == name:
            return doc
        return None

    def warn(self, text: str) -> None:
        self.warnings.append(text)

    def translate(self, context: str, text: str) -> str:
        return text


class _Doc:
    def __init__(self, name: str) -> None:
        self.Name = name


def _patch_port(monkeypatch, port: _RecordingPort) -> None:
    monkeypatch.setattr(gui_selection, "get_port", lambda _ctx=None: port)


def test_plain_item_uses_active_document(monkeypatch) -> None:
    active = _Doc("Active")

    class _Obj:
        Name = "Box"

    active.Box = _Obj()  # type: ignore[attr-defined]

    def get_object(doc, name):  # noqa: ANN001
        return doc.Box if name == "Box" else None  # type: ignore[attr-defined]

    port = _RecordingPort(active=active, open_docs={})
    port.get_object = get_object  # type: ignore[method-assign]
    _patch_port(monkeypatch, port)

    gui_selection.select_object_from_expression_item(ExpressionItem(object_name="Box", lhs="Box.Length", rhs="1"))
    assert port.selection == [("Active", "Box")]
    assert port.activated == []  # active-document path does not re-activate


def test_open_but_inactive_document_is_activated(monkeypatch) -> None:
    active = _Doc("Active")
    other = _Doc("Other")

    class _Obj:
        Name = "Box"

    def get_object(doc, name):  # noqa: ANN001
        if doc is other and name == "Box":
            return _Obj()
        return None

    port = _RecordingPort(active=active, open_docs={"Other": other})
    port.get_object = get_object  # type: ignore[method-assign]
    _patch_port(monkeypatch, port)

    item = ExpressionItem(object_name="Box", lhs="Box.Length", rhs="1", doc_id="Other", doc_label="Other")
    gui_selection.select_object_from_expression_item(item)
    assert port.activated == ["Other"]
    assert port.selection == [("Other", "Box")]


def test_closed_document_is_opened_for_jump(monkeypatch) -> None:
    opened = _Doc("Model")
    port = _RecordingPort(
        active=None,
        open_docs={},
        opened_files={"/data/Model.FCStd": opened},
    )

    class _Obj:
        Name = "Box"

    def get_object(doc, name):  # noqa: ANN001
        if doc is opened and name == "Box":
            return _Obj()
        return None

    port.get_object = get_object  # type: ignore[method-assign]
    _patch_port(monkeypatch, port)

    item = ExpressionItem(
        object_name="Box",
        lhs="Box.Length",
        rhs="Model#Params.kv",
        doc_id="Model",
        doc_label="Motor",
        doc_path="/data/Model.FCStd",
    )
    gui_selection.select_object_from_expression_item(item)
    assert port.opened == ["/data/Model.FCStd"]
    assert port.selection == [("Model", "Box")]


def test_failed_open_warns_and_does_not_select(monkeypatch) -> None:
    port = _RecordingPort(active=None, open_docs={}, opened_files={})
    _patch_port(monkeypatch, port)

    item = ExpressionItem(
        object_name="Box",
        lhs="Box.Length",
        rhs="x",
        doc_id="Model",
        doc_label="Motor",
        doc_path="/data/Missing.FCStd",
    )
    gui_selection.select_object_from_expression_item(item)
    assert port.selection == []
    assert port.warnings
