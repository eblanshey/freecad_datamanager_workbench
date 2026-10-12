"""Unit tests for the reference pattern matcher."""

from __future__ import annotations

from freecad.datamanager_wb.domain.expression_entry import (
    ENTRY_KIND_CELL,
    ENTRY_KIND_EXPRESSION,
    ExpressionEntry,
)
from freecad.datamanager_wb.scanning.reference_match import (
    ReferenceTarget,
    cross_document_patterns,
    entry_matches_target,
    internal_child_pattern,
    same_document_patterns,
)

TARGET = ReferenceTarget(
    doc_id="Drive",
    doc_label="Drive Model",
    object_name="Params",
    object_label="Parameters",
    child="height",
)


def _entry(doc: str, obj: str, lhs: str, rhs: str, kind: str = ENTRY_KIND_EXPRESSION) -> ExpressionEntry:
    return ExpressionEntry(source_doc=doc, kind=kind, object_name=obj, lhs=lhs, rhs=rhs)


def test_same_document_internal_varset_reference() -> None:
    entry = _entry("Drive", "Box", "Length", "Params.height * 2")
    assert entry_matches_target(entry, TARGET)


def test_same_document_label_reference() -> None:
    entry = _entry("Drive", "Box", "Length", "<<Parameters>>.height")
    assert entry_matches_target(entry, TARGET)


def test_internal_word_reference_only_counts_in_owning_object() -> None:
    """A bare `height` mention matches only inside the VarSet's own entries."""
    own = _entry("Drive", "Params", "width", "height + 1")
    other = _entry("Drive", "Box", "Length", "height + 1")
    assert entry_matches_target(own, TARGET)
    assert not entry_matches_target(other, TARGET)


def test_internal_word_reference_respects_boundaries() -> None:
    pattern = internal_child_pattern(TARGET)
    assert pattern is not None
    assert pattern.search("height + width")
    assert not pattern.search("heightMax")
    assert not pattern.search("myheight")


def test_cross_document_reference_by_name() -> None:
    entry = _entry("Other", "Box", "Length", "Drive#Params.height + 1")
    assert entry_matches_target(entry, TARGET)


def test_cross_document_reference_by_label() -> None:
    for text in ("<<Drive Model>>#Params.height", '"Drive Model"#Params.height'):
        entry = _entry("Other", "Box", "Length", text)
        assert entry_matches_target(entry, TARGET), text


def test_cross_document_reference_by_object_label() -> None:
    entry = _entry("Other", "Box", "Length", 'Drive#<<Parameters>>.height')
    assert entry_matches_target(entry, TARGET)


def test_bare_name_reference_does_not_match_across_documents() -> None:
    """Plain `Params.height` in another document must NOT count: each document
    may have its own `Params` object."""
    entry = _entry("Other", "Box", "Length", "Params.height * 2")
    assert not entry_matches_target(entry, TARGET)


def test_cross_document_clone_name_is_not_matched() -> None:
    entry = _entry("Other", "Box", "Length", "Drive#Params001.height")
    assert not entry_matches_target(entry, TARGET)
    entry2 = _entry("Other", "Box", "Length", "Drive#Params.heightMax")
    assert not entry_matches_target(entry2, TARGET)


def test_cell_entries_participate_in_matching() -> None:
    cross = _entry("Other", "Table", "B1", "=Drive#Params.height", ENTRY_KIND_CELL)
    assert entry_matches_target(cross, TARGET)


def test_whole_object_query_matches_any_child_path_cross_document() -> None:
    whole = ReferenceTarget(
        doc_id="Drive",
        doc_label="Drive Model",
        object_name="Params",
        object_label="Parameters",
        child=None,
    )
    entry = _entry("Other", "Box", "Length", "Drive#Params.height + 1")
    assert entry_matches_target(entry, whole)
    clone_entry = _entry("Other", "Box", "Length", "Drive#Params001.height")
    assert not entry_matches_target(clone_entry, whole)


def test_whole_object_same_document_query() -> None:
    whole = ReferenceTarget(
        doc_id="Drive",
        doc_label="Drive",
        object_name="Table",
        object_label="Table",
        child=None,
    )
    assert entry_matches_target(_entry("Drive", "Box", "L", "<<Table>>.A1"), whole)
    assert entry_matches_target(_entry("Drive", "Box", "L", "Table.A1"), whole)
    assert not entry_matches_target(_entry("Drive", "Box", "L", "TableX.A1"), whole)


def test_patterns_are_available_as_compiled_regexes() -> None:
    assert same_document_patterns(TARGET)
    patterns = cross_document_patterns(TARGET)
    assert patterns
    # every cross-document pattern anchors the child token on the right
    assert all(p.pattern.endswith("(?![A-Za-z0-9_])") for p in patterns)
    assert any(p.search("Drive#Params.height + 1") for p in patterns)
    assert not any(p.search("Drive#Params.heightMax") for p in patterns)
