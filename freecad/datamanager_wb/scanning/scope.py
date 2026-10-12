# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Document sources for cross-document reference searching.

Reference searching always covers every open (non-temporary) document, the
saved active document's directory tree (recursively — see
``DocumentScanner._project_folder_paths``), and the list of additional
**closed** ``.FCStd`` files managed by the user. VarSets, spreadsheets, and
their variables/aliases are still listed from the active document only — the
scope controls where *references* are searched, not where variables are
listed.

Scopes are persisted as a compact JSON string via the workbench settings port.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentScope:
    """Additional closed ``.FCStd`` files to include in reference searches.

    Attributes:
        extra_files: Absolute paths of closed documents to scan in addition to
            all open documents. Files belonging to already-open documents are
            ignored (the live document wins).
    """

    extra_files: tuple[str, ...] = ()

    @classmethod
    def empty(cls) -> "DocumentScope":
        """Return the default scope: all open documents only."""
        return cls()

    def to_json(self) -> str:
        """Serialize the scope for settings persistence."""
        return json.dumps({"files": list(self.extra_files)})

    @classmethod
    def from_json(cls, text: str) -> "DocumentScope":
        """Deserialize a scope; falls back to the default on any problem."""
        try:
            payload = json.loads(text)
            raw = payload.get("files") if isinstance(payload, dict) else payload
            files: list[str] = []
            if isinstance(raw, list):
                files = [str(item) for item in raw if isinstance(item, str) and item]
            return cls(extra_files=tuple(files))
        except (ValueError, TypeError, AttributeError):
            return cls.empty()
