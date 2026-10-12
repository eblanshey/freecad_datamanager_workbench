"""Shared fakes for unit tests: duck-typed FreeCAD documents and ports."""

from __future__ import annotations

from types import SimpleNamespace


class FakeApp:
    """Duck-typed `FreeCAD` module surface used through `FreeCadContext`."""

    def __init__(self, active: object | None = None, docs: list[object] | None = None) -> None:
        self.ActiveDocument = active
        self.Qt = SimpleNamespace(translate=lambda context, text: text)
        self.Console = SimpleNamespace(
            PrintMessage=lambda _t: None,
            PrintWarning=lambda _t: None,
            PrintLog=lambda _t: None,
        )
        self._docs = {str(getattr(d, "Name", "")): d for d in (docs or [])}
        if active is not None and str(getattr(active, "Name", "")) not in self._docs:
            self._docs[str(getattr(active, "Name", ""))] = active
        self.opened: list[str] = []
        self.activated: list[str] = []

    def listDocuments(self) -> dict[str, object]:  # noqa: N802 - FreeCAD API
        return dict(self._docs)

    def getDocument(self, name: str) -> object:  # noqa: N802 - FreeCAD API
        doc = self._docs.get(name)
        if doc is None:
            raise KeyError(name)
        return doc

    def openDocument(self, path: str) -> object:  # noqa: N802 - FreeCAD API
        self.opened.append(path)
        raise RuntimeError(f"no real file handling in tests: {path}")

    def setActiveDocument(self, name: str) -> None:  # noqa: N802 - FreeCAD API
        self.activated.append(name)


class FakeVarSet:
    TypeId = "App::VarSet"

    def __init__(self, name: str, label: str | None = None, variables: dict[str, str] | None = None, groups: dict[str, str] | None = None) -> None:
        self.Name = name
        self.Label = label or name
        self._variables = variables or {}
        self._groups = groups or {}
        self.PropertiesList = ["Label", "Label2", "Visibility"] + list(self._variables)
        self.ExpressionEngine: list[tuple[str, str]] = []

    def getGroupOfProperty(self, prop: str) -> str:  # noqa: N802 - FreeCAD API
        return self._groups.get(prop, "Base")


class FakeSheet:
    TypeId = "Spreadsheet::Sheet"

    def __init__(
        self,
        name: str,
        label: str | None = None,
        aliases: dict[str, str] | None = None,
        cells: dict[str, str] | None = None,
    ) -> None:
        self.Name = name
        self.Label = label or name
        self._aliases = aliases or {}
        self._cells = cells or {}
        self.ExpressionEngine: list[tuple[str, str]] = []

    def getAliases(self) -> dict[str, str]:  # noqa: N802 - FreeCAD API
        return dict(self._aliases)

    def getUsedCells(self) -> list[str]:  # noqa: N802 - FreeCAD API
        return list(self._cells)

    def getContents(self, cell: str) -> str:  # noqa: N802 - FreeCAD API
        return self._cells.get(cell, "")


class FakeObject:
    """Plain document object carrying an ExpressionEngine list."""

    def __init__(self, name: str, expressions: list[tuple[str, str]], type_id: str = "App::Feature") -> None:
        self.Name = name
        self.Label = name
        self.TypeId = type_id
        self.ExpressionEngine = expressions


class FakeDocument:
    def __init__(
        self,
        name: str,
        label: str | None = None,
        objects: list[object] | None = None,
        file_name: str = "",
        temporary: bool = False,
    ) -> None:
        self.Name = name
        self.Label = label or name
        self.FileName = file_name
        self.Temporary = temporary
        self.Objects = objects or []

    def getObject(self, name: str) -> object | None:  # noqa: N802 - FreeCAD API
        for obj in self.Objects:
            if getattr(obj, "Name", None) == name:
                return obj
        return None


class FakePort:
    """FreeCadPort-shaped fake exposing the document-level surface."""

    def __init__(self, active: object | None = None, open_docs: list[object] | None = None) -> None:
        self._active = active
        docs = list(open_docs or [])
        if active is not None and not any(getattr(d, "Name", None) == getattr(active, "Name", None) for d in docs):
            docs.insert(0, active)
        self._docs = {str(getattr(d, "Name", "")): d for d in docs}

    def get_active_document(self) -> object | None:
        return self._active

    def list_open_documents(self) -> list[object]:
        return list(self._docs.values())

    def get_open_document(self, doc_name: str) -> object | None:
        return self._docs.get(doc_name)

    def open_document_file(self, path: str) -> object | None:  # pragma: no cover - unused
        return None

    def try_set_active_document(self, doc_name: str) -> None:  # pragma: no cover - unused
        pass

    def get_object(self, doc: object, name: str) -> object | None:
        getter = getattr(doc, "getObject", None)
        return getter(name) if callable(getter) else None

    def get_typed_object(self, doc: object, name: str, *, type_id: str) -> object | None:
        obj = self.get_object(doc, name)
        if obj is None or getattr(obj, "TypeId", None) != type_id:
            return None
        return obj

    def warn(self, _text: str) -> None:
        pass

    def translate(self, _context: str, text: str) -> str:
        return text
