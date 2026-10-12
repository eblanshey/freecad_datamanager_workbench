"""Unit tests for the static .FCStd reader (closed documents)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from freecad.datamanager_wb.scanning.fcstd_file import FcstdReadError, read_fcstd

_DOCUMENT_XML = """<?xml version="1.0" encoding="utf-8"?>
<Document SchemaVersion="4">
  <Properties Count="2">
    <Property name="FileName" type="App::PropertyString"><String value="/somewhere/Model.FCStd"/></Property>
    <Property name="Label" type="App::PropertyString"><String value="DriveModel"/></Property>
  </Properties>
  <Objects Count="3">
    <Object type="App::VarSet" name="Params" id="1"/>
    <Object type="Spreadsheet::Sheet" name="Table" id="2"/>
    <Object type="Part::Box" name="Box" id="3"/>
  </Objects>
  <ObjectData>
    <Object name="Params">
      <Properties Count="4">
        <Property name="Label" type="App::PropertyString"><String value="Parameters"/></Property>
        <Property name="ExpressionEngine" type="App::PropertyExpressionEngine"/>
        <Property name="height" type="App::PropertyDistance" group="Dimensions" status="2097152"><Quantity value="10"/></Property>
        <Property name="width" type="App::PropertyDistance" group="Base"><Quantity value="5"/></Property>
      </Properties>
    </Object>
    <Object name="Table">
      <Properties Count="2">
        <Property name="cells" type="Spreadsheet::PropertySheet">
          <Cells Count="3" xlink="1">
            <Cell address="A1" content="=Params.height * 2" alias="double"/>
            <Cell address="B2" content="Driver"/>
            <Cell address="C3"/>
          </Cells>
        </Property>
      </Properties>
    </Object>
    <Object name="Box">
      <Properties Count="1">
        <Property name="ExpressionEngine" type="App::PropertyExpressionEngine">
          <ExpressionEngine count="2" xlink="1">
            <Expression path="Length" expression="Model#Params.height + 1"/>
            <Expression path="Placement.z" expression="&lt;&lt;Model&gt;&gt;#Params.width"/>
          </ExpressionEngine>
        </Property>
      </Properties>
    </Object>
  </ObjectData>
</Document>
"""


def _make_fcstd(path: Path, document_xml: str = _DOCUMENT_XML, extra: dict[str, str] | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", document_xml)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return path


def test_reads_document_label_and_derived_name(tmp_path: Path) -> None:
    fcstd = read_fcstd(str(_make_fcstd(tmp_path / "Model.FCStd")))
    assert fcstd.doc_name == "Model"
    assert fcstd.label == "DriveModel"
    assert fcstd.path.endswith("Model.FCStd")


def test_reads_varset_variables_with_groups(tmp_path: Path) -> None:
    fcstd = read_fcstd(str(_make_fcstd(tmp_path / "Model.FCStd")))
    assert len(fcstd.varsets) == 1
    varset = fcstd.varsets[0]
    assert varset.name == "Params"
    assert varset.label == "Parameters"
    assert varset.variables == {"height": "Dimensions", "width": "Base"}


def test_reads_sheet_aliases(tmp_path: Path) -> None:
    fcstd = read_fcstd(str(_make_fcstd(tmp_path / "Model.FCStd")))
    assert len(fcstd.sheets) == 1
    sheet = fcstd.sheets[0]
    assert sheet.name == "Table"
    assert sheet.aliases == {"double": "A1"}


def test_collects_expression_and_cell_entries(tmp_path: Path) -> None:
    fcstd = read_fcstd(str(_make_fcstd(tmp_path / "Model.FCStd")))
    expressions = {(e.object_name, e.lhs, e.rhs) for e in fcstd.entries if e.kind == "expression"}
    assert expressions == {
        ("Box", "Length", "Model#Params.height + 1"),
        ("Box", "Placement.z", "<<Model>>#Params.width"),
        # the sheet cell with an alias assignment is also an entry (kind=cell)
    }
    cells = {(e.object_name, e.lhs, e.rhs) for e in fcstd.entries if e.kind == "cell"}
    assert cells == {
        ("Table", "A1", "=Params.height * 2"),
        ("Table", "B2", "Driver"),
    }
    # C3 has no content -> skipped; aliases without content still registered above.


def test_expression_entries_carry_source_document(tmp_path: Path) -> None:
    fcstd = read_fcstd(str(_make_fcstd(tmp_path / "Model.FCStd")))
    assert all(e.source_doc == "Model" for e in fcstd.entries)


def test_label_falls_back_to_file_stem(tmp_path: Path) -> None:
    xml = _DOCUMENT_XML.replace('<String value="DriveModel"/>', '<String value=""/>')
    fcstd = read_fcstd(str(_make_fcstd(tmp_path / "Cool.FCStd", xml)))
    assert fcstd.label == "Cool"


def test_document_name_is_sanitized_identifier(tmp_path: Path) -> None:
    fcstd = read_fcstd(str(_make_fcstd(tmp_path / "my-model v2.FCStd")))
    assert fcstd.doc_name == "my_model_v2"


def test_missing_document_xml_raises(tmp_path: Path) -> None:
    path = tmp_path / "Broken.FCStd"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("GuiDocument.xml", "<GuiDocument/>")
    with pytest.raises(FcstdReadError):
        read_fcstd(str(path))


def test_unparsable_document_xml_raises(tmp_path: Path) -> None:
    path = tmp_path / "Junk.FCStd"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", "<Document><unclosed>")
    with pytest.raises(FcstdReadError):
        read_fcstd(str(path))


def test_nonexistent_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FcstdReadError):
        read_fcstd(str(tmp_path / "missing.FCStd"))


def test_document_without_objects_yields_empty_collections(tmp_path: Path) -> None:
    xml = '<?xml version="1.0" encoding="utf-8"?><Document><Properties/></Document>'
    fcstd = read_fcstd(str(_make_fcstd(tmp_path / "Empty.FCStd", xml)))
    assert fcstd.varsets == ()
    assert fcstd.sheets == ()
    assert fcstd.entries == ()


REPO_FIXTURE = Path(__file__).resolve().parents[1] / "freecad" / "varset_test.FCStd"


@pytest.mark.skipif(not REPO_FIXTURE.exists(), reason="bundled .FCStd fixture missing")
def test_reads_real_saved_document() -> None:
    """Parse the repository's real FreeCAD-saved .FCStd fixture."""
    fcstd = read_fcstd(str(REPO_FIXTURE))
    assert fcstd.doc_name == "varset_test"
    assert fcstd.label == "varset_test"

    assert len(fcstd.varsets) == 1
    varset = fcstd.varsets[0]
    assert varset.name == "VarSet"
    # real saved group attributes
    assert varset.variables["WallThickness"] == "Dimensions"
    assert varset.variables["UseScrews"] == "Options"
    assert varset.variables["OverallX"] == "OverallSize"
    assert varset.variables["Ribs"] == "Base"
    # built-ins excluded
    assert "Label" not in varset.variables
    assert "ExpressionEngine" not in varset.variables
    assert "Visibility" not in varset.variables
