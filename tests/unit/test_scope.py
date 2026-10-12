"""Unit tests for the reference-search document scope model."""

from __future__ import annotations

from freecad.datamanager_wb.scanning.scope import DocumentScope


def test_empty_scope_has_no_extra_files() -> None:
    scope = DocumentScope.empty()
    assert scope.extra_files == ()


def test_json_roundtrip() -> None:
    scope = DocumentScope(extra_files=("/data/Model.FCStd", "/other/Drive.FCStd"))
    parsed = DocumentScope.from_json(scope.to_json())
    assert parsed == scope


def test_from_json_falls_back_to_empty_on_garbage() -> None:
    assert DocumentScope.from_json("not json").extra_files == ()
    assert DocumentScope.from_json("").extra_files == ()
    assert DocumentScope.from_json('{"mode": "bogus"}').extra_files == ()


def test_from_json_skips_invalid_entries() -> None:
    payload = '{"files": ["/ok/Model.FCStd", 42, ""]}'
    scope = DocumentScope.from_json(payload)
    assert scope.extra_files == ("/ok/Model.FCStd",)


def test_from_json_accepts_bare_list() -> None:
    scope = DocumentScope.from_json('["/a.FCStd", "/b.FCStd"]')
    assert scope.extra_files == ("/a.FCStd", "/b.FCStd")
