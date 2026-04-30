"""Add tools/persona-reference-gen/ to sys.path for these unit tests.

The hyphen-named tool directory is not importable as a package; tests
import the modules directly off the path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOL_DIR = Path(__file__).resolve().parents[3] / "tools" / "persona-reference-gen"
if str(_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOL_DIR))
