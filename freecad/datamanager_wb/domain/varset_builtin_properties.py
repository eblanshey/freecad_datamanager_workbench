# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Property names that are not VarSet variables.

A VarSet stores its user variables as dynamic properties. The property list of a
VarSet object also contains built-in FreeCAD properties which must not be
presented as variables. This module is the single source of truth for that
exclusion list, shared by the live-document scanner and the static ``.FCStd``
reader.
"""

from __future__ import annotations

EXCLUDED_VARSET_PROPERTIES = frozenset(
    {
        "ExpressionEngine",
        "Label",
        "Label2",
        "Visibility",
        "Placement",
        "Group",
        "Material",
        "Proxy",
        "Shape",
        "State",
        "ViewObject",
    }
)


def is_excluded_varset_property(prop: object) -> bool:
    """Return True when a property name is a built-in, not a variable."""
    return str(prop) in EXCLUDED_VARSET_PROPERTIES
