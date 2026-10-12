# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""FreeCAD runtime context abstraction.

This module provides small Protocol interfaces for the parts of the FreeCAD API
used by this workbench, plus a `FreeCadContext` wrapper that can be injected
into non-UI code for testing.

Use `get_runtime_context()` to obtain the real runtime bindings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class QtLike(Protocol):
    """Minimal Protocol for FreeCAD's translation API (App.Qt)."""

    def translate(self, context: str, text: str) -> str:
        """Translate the given text in the provided translation context."""
        ...


class ConsoleLike(Protocol):
    """Minimal Protocol for FreeCAD's console output API (App.Console)."""

    def PrintMessage(self, text: str) -> None:
        """Print a message to the FreeCAD report view / console."""
        ...


class DocumentLike(Protocol):
    """Minimal Protocol for a loaded FreeCAD document."""

    Name: str
    Label: str
    FileName: str
    Temporary: bool
    Objects: list[object]

    def getObject(self, name: str) -> object | None:
        """Return a document object by name, or None if it does not exist."""
        ...


class AppLike(Protocol):
    """Minimal Protocol for the FreeCAD application module (App)."""

    ActiveDocument: DocumentLike | None
    Qt: QtLike
    Console: ConsoleLike

    def listDocuments(self) -> dict[str, DocumentLike]:
        """Return all loaded documents keyed by name."""
        ...

    def getDocument(self, name: str) -> DocumentLike:
        """Return a loaded document by name, raising when absent."""
        ...

    def openDocument(self, path: str) -> DocumentLike:
        """Load a document file and return the opened document."""
        ...

    def setActiveDocument(self, name: str) -> None:
        """Activate a loaded document by name."""
        ...


class GuiLike(Protocol):
    """Minimal Protocol for the FreeCAD GUI module (Gui)."""

    pass


@dataclass(frozen=True)
class FreeCadContext:
    """Bundle of runtime bindings used by this workbench.

    This wrapper allows code to be written against Protocols and enables unit
    tests to provide a fake context without importing FreeCAD.
    """

    app: AppLike
    gui: GuiLike | None = None


def get_runtime_context() -> FreeCadContext:
    """Return a context wired to the real FreeCAD runtime modules."""
    import FreeCAD as App

    try:
        import FreeCADGui as Gui
    except Exception:  # pylint: disable=broad-exception-caught
        Gui = None

    return FreeCadContext(app=App, gui=Gui)
