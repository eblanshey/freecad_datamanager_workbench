"""Presenter and display-model tests for document-qualified expression items."""

from __future__ import annotations

from freecad.datamanager_wb.domain.expression_item import ExpressionItem
from freecad.datamanager_wb.domain.parent_child_ref import ParentChildRef
from freecad.datamanager_wb.ui.main_panel_presenter import MainPanelPresenter


class _FakeController:
    """Mirrors `PanelController.get_object_label` qualification behavior."""

    def __init__(self, labels: dict[str, str]) -> None:
        self._labels = labels

    def get_object_label(self, object_name: str) -> str | None:
        return self._labels.get(object_name)


def _presenter(labels: dict[str, str]) -> MainPanelPresenter:
    return MainPanelPresenter(_FakeController(labels))


def _external_item() -> ExpressionItem:
    return ExpressionItem(
        object_name="Box",
        lhs="Box.Length",
        rhs="Model#Params.kv",
        doc_id="Model",
        doc_label="Motor",
    )


def test_display_text_without_document_is_unchanged() -> None:
    item = ExpressionItem(object_name="Box", lhs="Box.Length", rhs="Params.width")
    assert item.display_text == "Box.Length = Params.width"


def test_display_text_qualifies_external_documents() -> None:
    assert _external_item().display_text == "Motor.Box.Length = Model#Params.kv"


def test_presenter_name_mode_uses_document_name() -> None:
    presenter = _presenter({})
    assert (
        presenter.format_expression_item(_external_item(), use_label=False)
        == "Model.Box.Length = Model#Params.kv"
    )


def test_presenter_label_mode_uses_document_and_object_labels() -> None:
    presenter = _presenter({"Model#Box": "Model#Boxy"})
    item = ExpressionItem(
        object_name="Box",
        lhs="Box.Length",
        rhs="1",
        doc_id="Model",
        doc_label="Motor",
    )
    assert presenter.format_expression_item(item, use_label=True) == "Motor.Boxy.Length = 1"


def test_presenter_label_mode_falls_back_when_label_missing() -> None:
    presenter = _presenter({})
    item = ExpressionItem(
        object_name="Box",
        lhs="Box.Length",
        rhs="1",
        doc_id="Model",
        doc_label="Motor",
    )
    assert presenter.format_expression_item(item, use_label=True) == "Motor.Box.Length = 1"


def test_presenter_same_document_items_render_plain() -> None:
    presenter = _presenter({"Box": "Boxy"})
    item = ExpressionItem(object_name="Box", lhs="Box.Length", rhs="Params.kv")
    assert presenter.format_expression_item(item, use_label=False) == "Box.Length = Params.kv"
    assert presenter.format_expression_item(item, use_label=True) == "Boxy.Length = Params.kv"


def test_presenter_formats_qualified_parent_labels() -> None:
    """Qualified parents render with their (document-qualified) labels."""
    presenter = _presenter({"Model#Params": "Motor#Motor Params"})
    ref = ParentChildRef(parent="Model#Params", child="kv")
    assert (
        presenter.format_parent_child_ref(ref, use_label=True) == "Motor#Motor Params.kv"
    )
    # name mode keeps the raw qualified text
    assert presenter.format_parent_child_ref(ref, use_label=False) == "Model#Params.kv"


def test_presenter_formats_qualified_parent_names() -> None:
    presenter = _presenter({"Model#Params": "Motor#Motor Params"})
    assert (
        presenter.format_object_name("Model#Params", use_label=True) == "Motor#Motor Params"
    )
    assert presenter.format_object_name("Model#Params", use_label=False) == "Model#Params"


def test_presenter_handles_qualified_group_suffix() -> None:
    presenter = _presenter({"Model#Params": "Motor#Motor Params"})
    assert (
        presenter.format_object_name("Model#Params.Dimensions", use_label=True)
        == "Motor#Motor Params.Dimensions"
    )
