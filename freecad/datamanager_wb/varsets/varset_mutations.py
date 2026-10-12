# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Mutation helpers for FreeCAD VarSets.

Contains operations that modify VarSets, such as removing a variable property.
"""

from ..domain.qualified_parent import split_parent_name
from ..ports.freecad_context import FreeCadContext
from ..ports.freecad_port import get_port


def _has_property(obj: object, property_name: str) -> bool:
    props = set(getattr(obj, "PropertiesList", []) or [])
    return property_name in props


def _try_remove_property(obj: object, property_name: str) -> bool:
    remover = getattr(obj, "removeProperty", None)
    if not callable(remover):
        return False
    try:
        remover(property_name)
    except Exception:  # pylint: disable=broad-exception-caught
        return False
    return True


def removeVarsetVariable(
    varset_name: str,
    variable_name: str,
    *,
    ctx: FreeCadContext | None = None,
    doc: object | None = None,
) -> bool:
    """Remove a variable/property from a VarSet.

    Args:
        varset_name: Name of the `App::VarSet` object (a `Document#`-qualified
            spec is accepted; the qualifier only selects the document).
        variable_name: Name of the property to remove.
        doc: Optional document to operate on; defaults to the active document.

    Returns:
        ``True`` if the property was removed, otherwise ``False``.
    """
    port = get_port(ctx)
    if doc is None:
        doc = port.get_active_document()
    if doc is None:
        return False

    _doc_id, bare_name = split_parent_name(varset_name)
    varset = port.get_typed_object(doc, bare_name, type_id="App::VarSet")
    if varset is None:
        return False

    if not _has_property(varset, variable_name):
        return False

    return _try_remove_property(varset, variable_name)
