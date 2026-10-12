# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""End-to-end cross-document check inside FreeCAD (developer QA).

Builds two documents with real cross-document expressions, saves and closes
them, then verifies the scanning layer finds every reference from the closed
files (and from a partially reopened state).

Run with a console-mode FreeCAD interpreter, e.g. (AppImage layout)::

    FREECAD=<extracted AppImage root>
    PYTHONPATH=$FREECAD/usr/lib/python3.11/site-packages:$FREECAD/usr/lib:$FREECAD/usr/Ext \
    LD_LIBRARY_PATH=$FREECAD/usr/lib QT_QPA_PLATFORM=offscreen \
    $FREECAD/usr/bin/python scripts/crossdoc_integration_check.py "$(pwd)"

Prints INTEGRATION_OK on success.
"""

import os
import sys
import tempfile
import zipfile
from xml.etree import ElementTree

import FreeCAD as App

REPO = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
sys.path.insert(0, os.path.join(REPO, 'freecad'))

# Import the in-repo workbench directly (its internal relative imports only
# go within datamanager_wb), avoiding the installed-addon shadowing.

tmp = tempfile.mkdtemp(prefix="dm_xref_")

# Workbench imports (in-repo, avoiding installed-addon shadowing).
from datamanager_wb.domain.parent_child_ref import ParentChildRef  # noqa: E402
from datamanager_wb.scanning.scanner import DocumentScanner  # noqa: E402
from datamanager_wb.scanning.scope import DocumentScope  # noqa: E402
from datamanager_wb.spreadsheets import spreadsheet_query  # noqa: E402
from datamanager_wb.varsets import varset_query  # noqa: E402
from datamanager_wb.varsets.varset_datasource import VarsetDataSource  # noqa: E402

drive_path = os.path.join(tmp, "Drive.FCStd")
consumer_path = os.path.join(tmp, "Consumer.FCStd")

# --- build Drive: VarSet + spreadsheet -------------------------------------
drive = App.newDocument("Drive")
params = drive.addObject("App::VarSet", "Params")
params.Label = "Parameters"
params.addProperty("App::PropertyLength", "height", "Base")
params.setExpression("height", "42")  # assignment (literal), not a reference
params.addProperty("App::PropertyLength", "height2", "Base")
params.setExpression("height2", "height * 2")  # internal sibling reference by bare name
table = drive.addObject("Spreadsheet::Sheet", "Table")
table.set("A1", "7")
table.setAlias("A1", "width")
table.set("B1", "=width * 2")  # internal alias reference
table.set("E1", "'width")  # definition-style row (quoted alias text)
drive.recompute()
drive.saveAs(drive_path)

# --- build Consumer: references into Drive ----------------------------------
consumer = App.newDocument("Consumer")
consumer.saveAs(consumer_path)  # owner must exist on disk before xlink expressions
box = consumer.addObject("App::FeaturePython", "Box")
box.addProperty("App::PropertyLength", "Length")
box.setExpression("Length", "Drive#Params.height + 1")

sheet = consumer.addObject("Spreadsheet::Sheet", "Notes")
sheet.set("A1", "7")  # content without ref
sheet.set("C3", "=Drive#Table.width")  # cross-doc alias in a cell
consumer.recompute()
consumer.save()

# --- build Bracket in a subdirectory: only reachable via the project glob ---
project_dir = os.path.join(tmp, "project")
os.makedirs(project_dir, exist_ok=True)
bracket_path = os.path.join(project_dir, "Bracket.FCStd")
bracket = App.newDocument("Bracket")
bracket.saveAs(bracket_path)
arm = bracket.addObject("App::FeaturePython", "Arm")
arm.addProperty("App::PropertyLength", "Len")
arm.setExpression("Len", "Drive#Params.height * 3")
bracket.recompute()
bracket.save()

errors = []


def check(label, condition, detail=""):
    if not condition:
        errors.append(f"FAIL {label} {detail}")
        print(f"FAIL {label} {detail}")
    else:
        print(f"ok   {label}")


class _AppPortShim:
    """Smallest object satisfying DocumentScanner's port usage in closed-file mode."""

    def get_active_document(self):
        return App.ActiveDocument

    def list_open_documents(self):
        return list(App.listDocuments().values())

    def get_open_document(self, name):
        try:
            return App.getDocument(name)
        except Exception:
            return None


scanner = DocumentScanner(_AppPortShim())

# 1a) With BOTH documents open, parents are listed from the active document
# only, while references are found across all open documents.
App.setActiveDocument("Drive")
check(
    "varsets listed from active document only",
    list(varset_query.getVarsets(scanner=scanner)) == ["Params"],
)
check(
    "spreadsheets listed from active document only",
    list(spreadsheet_query.getSpreadsheets(scanner=scanner)) == ["Table"],
)
ds = VarsetDataSource(scanner=scanner)
items_live, counts_live = ds.get_expression_items(
    [ParentChildRef(parent="Drive#Params", child="height")]
)
displays = {item.display_text for item in items_live}
print("live expression displays:", displays)
check(
    "external hit renders document-qualified",
    "Consumer.Box.Length = Drive#Params.height + 1" in displays,
    str(displays),
)
check(
    "same-document hit renders plain",
    "Params.height2 = height * 2" in displays,
    str(displays),
)
check(
    "counts include cross-document usages",
    counts_live.get("Drive#Params.height") == 3,  # Consumer + Bracket(project/) + internal
    str(counts_live),
)
check(
    "auto project folder finds subdir file while documents are open",
    "Bracket.Arm.Len = Drive#Params.height * 3" in displays,
    str(displays),
)

# 1b) The expression that FreeCAD persisted for the cross-document reference.
with zipfile.ZipFile(consumer_path) as zf:
    root = ET_root = ElementTree.fromstring(zf.read("Document.xml"))
exprs = []
for obj in root.find("ObjectData"):
    for prop in obj.find("Properties"):
        if prop.attrib.get("name") == "ExpressionEngine":
            engine = prop.find("ExpressionEngine")
            if engine is not None:
                for e in engine.findall("Expression"):
                    exprs.append((obj.attrib.get("name"), e.attrib.get("path"), e.attrib.get("expression")))
cells = []
for obj in root.find("ObjectData"):
    for prop in obj.find("Properties"):
        if prop.attrib.get("name") == "cells":
            c = prop.find("Cells")
            if c is not None:
                for cell in c.findall("Cell"):
                    cells.append((obj.attrib.get("name"), cell.attrib.get("address"), cell.attrib.get("content"), cell.attrib.get("alias")))
print("persisted expressions:", exprs)
print("persisted cells:", cells)
check("xlink expression persisted", any(("Drive" in (e[2] or "")) or ("#" in (e[2] or "")) for e in exprs), str(exprs))
check("cell content persisted", any("Drive#" in (c[2] or "") for c in cells), str(cells))

# 2) Close all documents; scan them purely as closed files.
App.closeDocument("Bracket")
App.closeDocument("Consumer")
App.closeDocument("Drive")

scope = DocumentScope(extra_files=(drive_path, consumer_path))

targets = scanner.resolve(scope)
ids = {t.doc_id for t in targets}
check("both closed docs scanned", ids == {"Drive", "Consumer"}, str(ids))

hits = varset_query.getVarsetReferences("Drive#Params", "height", scope=scope, scanner=scanner)
hit_ids = {(h.doc_id, h.lhs, h.source) for h in hits}
print("varset hits:", hit_ids)
check("consumer hits closed drive varset", ("Consumer", "Box.Length", "file") in hit_ids)
check("owner internal sibling hit", ("Drive", "Params.height2", "file") in hit_ids)
check("assignment expression is not a reference", ("Drive", "Params.height", "file") not in hit_ids)

alias_hits = spreadsheet_query.getSpreadsheetAliasReferences("Drive#Table", "width", scope=scope, scanner=scanner)
alias_ids = {(h.doc_id, h.lhs, h.source) for h in alias_hits}
print("alias hits:", alias_ids)
check("consumer cell hits closed drive alias", ("Consumer", "Notes.C3", "file") in alias_ids)
check("owner definition-style row hit", ("Drive", "Table.E1", "file") in alias_ids)
check("plain value cell is not a reference", ("Drive", "Table.A1", "file") not in alias_ids)
check("owner internal formula hit", ("Drive", "Table.B1", "file") in alias_ids)

names = list(varset_query.getVarsets(scope=scope, scanner=scanner))
check("varsets not listed from closed docs", names == [], str(names))
groups = varset_query.getVarsetVariableGroups("Drive#Params", scope=scope, scanner=scanner)
check("varset variables from closed file", groups == {"height": "Base", "height2": "Base"}, str(groups))
sheet_names = list(spreadsheet_query.getSpreadsheets(scope=scope, scanner=scanner))
check("sheets not listed from closed docs", sheet_names == [], str(sheet_names))

# 3) Reopen only Consumer; Drive stays a registered closed file. FreeCAD
# auto-opens documents referenced via xlink when restoring Consumer, so the
# file entry must dedupe to the live (open) Drive document.
consumer2 = App.openDocument(consumer_path)
scope2 = DocumentScope(extra_files=(drive_path,))
hits2 = varset_query.getVarsetReferences("Drive#Params", "height", scope=scope2, scanner=scanner)
srcs2 = {(h.doc_id, h.source) for h in hits2}
# FreeCAD auto-opened Drive via the xlink when restoring Consumer, so the file
# entry must dedupe to the live document; Bracket is picked up by the auto
# project-folder glob of the saved active Consumer.
check(
    "open consumer + reopened drive dedupes to live scan",
    srcs2 == {("Consumer", "open"), ("Drive", "open"), ("Bracket", "file")},
    str(srcs2),
)
for _name in ("Consumer", "Drive", "Bracket"):
    try:
        App.closeDocument(_name)
    except Exception:
        pass

# 4) Auto project-folder search: reopen ONLY Drive (the saved active
# document). Its directory tree must be searched with no registered files:
# Consumer is a sibling file, Bracket lives in a subdirectory.
App.openDocument(drive_path)
App.setActiveDocument("Drive")
targets4 = scanner.resolve(DocumentScope.empty())
ids4 = {t.doc_id for t in targets4}
check(
    "project folder auto-includes siblings and subdirs",
    ids4 == {"Drive", "Consumer", "Bracket"},
    str(ids4),
)
hits4 = varset_query.getVarsetReferences("Params", "height", scanner=scanner)
srcs4 = {(h.doc_id, h.source) for h in hits4}
print("auto-folder hits:", srcs4)
check(
    "hits found via auto project folder",
    srcs4 == {("Drive", "open"), ("Consumer", "file"), ("Bracket", "file")},
    str(srcs4),
)
check(
    "varsets still listed from active document only",
    list(varset_query.getVarsets(scanner=scanner)) == ["Params"],
)

if errors:
    print("INTEGRATION_FAILED")
    sys.exit(1)
print("INTEGRATION_OK", tmp)
