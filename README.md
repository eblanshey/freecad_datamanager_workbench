# DataManager FreeCAD Workbench - Forked

**This is a fork from https://github.com/royw/freecad_datamanager_workbench. It is vibe-coded to add the following functionality:**

- Show expressions from other documents, even if they are not currently open in FreeCAD

[![Docs](https://github.com/royw/freecad_datamanager_workbench/actions/workflows/docs.yml/badge.svg)](https://github.com/royw/freecad_datamanager_workbench/actions/workflows/docs.yml)

Manages FreeCAD VarSets and aliases.

Tested on FreeCAD version 1.0.2 and 1.1.0rc2.

Documentation: [royw.github.io/freecad_datamanager_workbench](https://royw.github.io/freecad_datamanager_workbench/)

Special thanks to OldBeard for his testing of the beta workbench and many great suggestions!

## Suggestion FreeCAD Preferences

- Enable: General --> Selection --> Tree Selection Behavior --> Auto expand tree item when the corresponding object is selected in the 3D view.

## Installation

Add instructions for installing via the Addon Manager.

## Usage

The workbench appears in the FreeCAD workbench selector as **Data Manager**.

![DataManager workbench annotated UI](docs/images/datamanager_wb_annotated.png)

Annotated UI legend:

1. Workbench selection (workbench selector, Data Manager menu, and toolbar icons)
1. VarSets and Aliases tabs
1. Available VarSets
1. VarSets filter
1. Exclude CopyOnChanged varsets checkbox
1. Variables list
1. Only Unused checkbox
1. Remove Selected Unused Variables button
1. Splitter (resizable pane divider)
1. Expressions list
1. Show Objects as: Name/Label radio buttons
1. Copy Selection Buttons
1. Shows selected expression selects object in model view

### VarSets tab

- **VarSets list** (3)

  - Select one or more VarSets to populate the Variables list.
  - If a VarSet contains variables in multiple groups, the list may also include virtual entries like
    `VarSetName.GroupName`. Selecting a virtual entry filters the Variables list to that group.

- **VarSets filter** (4)

  - Filters VarSets by name using a glob match.
  - If you type no glob characters, the filter is treated as a substring match.

- **Exclude CopyOnChanged varsets** (5)

  - When you create Links to objects referencing a VarSet, FreeCAD may create hidden *copy-on-change* groups (typically `CopyOnChangeGroup*`) and generate copied VarSets (e.g. `VarSet001`).
  - Enabling this option hides those generated copies so the list focuses on the VarSets you created.

- **Variables filter**

  - Filters variables by variable name using a glob match.
  - The match is against the variable name only (not the `VarSetName.` prefix).

- **Only Unused** (7)

  - Shows only variables that have **no** expression references.

- **Remove Selected Unused Variables** (8)

  - Removes the selected unused variables from the VarSet.

- **Expressions list** (10)

  - Shows the expressions that reference each variable.
  - Clicking an expression selects the Object in the Model tree.
  - The list is resizable using a splitter (9).
  - Use the **Show Objects as: Name/Label** radio buttons (11) to control whether expression list entries display
    the FreeCAD object internal name or its label. The choice is persisted.

- **Copy Selected** (12)

  - Each list pane includes a Copy Selected button.
  - Clicking it copies the selected list items to the clipboard (one item per line).
  - You can also right-click a list to use **Copy** (and **Select All** where applicable).

- **Select object in model tree from expression** (13)

  - Clicking an expression entry attempts to select the referenced object in the FreeCAD model tree.

### Aliases tab

- The Aliases tab mirrors the VarSets layout and is resizable using a splitter.
- Alias definition rows are displayed using `:=` to distinguish definition from a normal expression (for example:
  `Spreadsheet.A1 := 'MyAlias`).
- The **Show Objects as: Name/Label** setting is independent from the VarSets tab and is persisted.

### Cross-document references

Selecting a variable lists **every expression that uses it**, in the active
document, in every other open document (hidden/temporary helper documents
opened automatically by links are ignored), in the **project folder** (every
`.FCStd` under the saved active document's directory, recursively), and in
any additional closed `.FCStd` files you register via **Add closed
documents…** in the toolbar row. The VarSets/Spreadsheets/variables lists
always come from the active document only — other documents contribute
references, not list entries.

Closed documents are read directly from disk (the saved `Document.xml` inside
the `.FCStd` archive), so references are found without opening them. Unsaved
in-memory edits are of course not visible to the file scan; that is why the
project folder is only picked up once the active document has been saved at
least once.

Expression entries that live in another document are shown
document-qualified — for example `Document2.Pad.Length = Document#Varset.MyVar`
— using FreeCAD's own external-reference syntax `Document#Object.Property` for
matching, so objects with colliding names in different documents never mix.
Clicking a reference that lives in a closed document opens it and selects the
referencing object.

The closed-file list is persisted between sessions.
