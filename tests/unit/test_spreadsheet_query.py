"""Unit tests for spreadsheet alias query helpers (cross-document aware)."""

from __future__ import annotations

from freecad.datamanager_wb.scanning import reference_match
from freecad.datamanager_wb.spreadsheets import spreadsheet_query
from fakes import FakeDocument, FakePort, FakeSheet


def test_normalize_alias_map_inverts_when_keys_are_cells() -> None:
    """The re-exported alias-map normalizer inverts a cell->alias mapping."""
    raw = {"A1": "foo", "B2": "bar"}
    assert spreadsheet_query._normalize_alias_map(raw) == {"foo": "A1", "bar": "B2"}


def test_normalize_alias_map_keeps_alias_to_cell_mapping() -> None:
    """The alias-map normalizer preserves an alias->cell mapping."""
    raw = {"foo": "A1", "bar": "B2"}
    assert spreadsheet_query._normalize_alias_map(raw) == raw


def test_same_document_alias_patterns_respect_word_boundaries() -> None:
    """Alias references must match whole identifiers, not prefixes."""
    target = reference_match.ReferenceTarget(
        doc_id="Doc", doc_label="Doc", object_name="Sheet", object_label="Sheet", child="foo"
    )
    patterns = reference_match.same_document_patterns(target)

    assert any(p.search("Sheet.foo + 1") for p in patterns)
    assert any(p.search("<<Sheet>>.foo") for p in patterns)
    # "foobar" must not match the alias "foo" (right-hand identifier boundary)
    assert not any(p.search("Sheet.foobar + 1") for p in patterns)
    # a longer name with the same suffix still matches the substring token,
    # mirroring the historical behavior of the single-document matcher
    assert any(p.search("MySheet.foo") for p in patterns)


def test_alias_word_boundary_only_applies_inside_the_owning_sheet() -> None:
    """Bare alias names count only in the owning sheet's own entries."""
    target = reference_match.ReferenceTarget(
        doc_id="Doc", doc_label="Doc", object_name="Sheet", object_label="Sheet", child="foo"
    )
    internal = reference_match.internal_child_pattern(target)
    assert internal is not None
    assert internal.search("foo + 1")
    assert not internal.search("foobar + 1")


def _doc_with_params() -> FakeDocument:
    params = FakeSheet("Params", aliases={"BoomSegments": "B1"}, cells={"B1": "BoomSegments"})
    clone = FakeSheet("Params001", aliases={"BoomSegments": "B1"}, cells={"B1": "BoomSegments"})
    from fakes import FakeObject

    return FakeDocument(
        "Doc",
        objects=[
            params,
            clone,
            FakeObject("LinearPattern", [("Occurrences", "<<Params>>.BoomSegments")]),
            FakeObject("LinearPattern013", [("Occurrences", "<<Params001>>.BoomSegments")]),
        ],
    )


def test_get_spreadsheet_alias_references_does_not_match_other_spreadsheet_prefix(monkeypatch) -> None:
    """Alias references to Params must not match clones like Params001."""
    doc = _doc_with_params()
    fake_port = FakePort(active=doc, open_docs=[doc])
    monkeypatch.setattr(spreadsheet_query, "get_port", lambda _ctx=None: fake_port)

    hits = spreadsheet_query.getSpreadsheetAliasReferences("Params", "BoomSegments")
    # B1 is the alias definition cell (owner sheet -> internal match)
    assert {(hit.doc_id, hit.lhs) for hit in hits} == {
        ("Doc", "LinearPattern.Occurrences"),
        ("Doc", "Params.B1"),
    }


def test_alias_reference_counts_include_other_open_documents(monkeypatch) -> None:
    """A cross-document expression in another open document counts as a reference."""
    owner = _doc_with_params()

    from fakes import FakeObject

    other = FakeDocument(
        "Driver",
        objects=[FakeObject("Box", [("Length", "Doc#Params.BoomSegments")])],
    )
    fake_port = FakePort(active=owner, open_docs=[owner, other])
    monkeypatch.setattr(spreadsheet_query, "get_port", lambda _ctx=None: fake_port)

    hits = spreadsheet_query.getSpreadsheetAliasReferences("Params", "BoomSegments")
    assert ("Driver", "Box.Length") in {(hit.doc_id, hit.lhs) for hit in hits}
    assert all(hit.owner_doc_id == "Doc" for hit in hits)


def test_spreadsheets_listed_from_active_document_only(monkeypatch) -> None:
    """Other open documents never add parent entries."""
    doc_a = _doc_with_params()
    doc_b = FakeDocument("Second", objects=[FakeSheet("Params")])
    fake_port = FakePort(active=doc_a, open_docs=[doc_a, doc_b])
    monkeypatch.setattr(spreadsheet_query, "get_port", lambda _ctx=None: fake_port)

    names = list(spreadsheet_query.getSpreadsheets())
    assert sorted(names) == ["Params", "Params001"]


def test_get_spreadsheet_alias_names_for_active_sheet(monkeypatch) -> None:
    """Alias names come from the sheet resolved against the active document."""
    doc = _doc_with_params()
    fake_port = FakePort(active=doc, open_docs=[doc])
    monkeypatch.setattr(spreadsheet_query, "get_port", lambda _ctx=None: fake_port)

    names = spreadsheet_query.getSpreadsheetAliasNames("Params")
    assert names == ["BoomSegments"]
