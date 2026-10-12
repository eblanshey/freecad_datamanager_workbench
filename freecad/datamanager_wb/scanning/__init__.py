# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the DataManager addon.

"""Cross-document reference scanning.

This package collects everything needed to search for references across more
than the active document:

- :mod:`.scope` — the document scope model (active / all open / selected),
- :mod:`.fcstd_file` — a pure-Python reader for closed ``.FCStd`` files,
- :mod:`.scanner` — resolves a scope into unified scan targets (live + file),
- :mod:`.reference_match` — pattern matching rules for same-document and
  cross-document (``Document#Object.Property``) references.

The static reading approach (parsing ``Document.xml`` from the zip archive)
follows the design proven by the `fcxref` project by G. Roques
(LGPL-2.1+); this is an independent implementation aligned with this
workbench's architecture.
"""

from .fcstd_file import FcstdDocument, read_fcstd
from .reference_match import ReferenceTarget, entry_matches_target
from .scanner import DocumentScanner, ScanSheet, ScanTarget, ScanVarSet
from .scope import DocumentScope

__all__ = [
    "DocumentScanner",
    "DocumentScope",
    "FcstdDocument",
    "ReferenceTarget",
    "ScanSheet",
    "ScanTarget",
    "ScanVarSet",
    "entry_matches_target",
    "read_fcstd",
]
