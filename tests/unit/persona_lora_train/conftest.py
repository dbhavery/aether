"""Add tools/persona-lora-train/ to sys.path for these unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

_TOOL_DIR = Path(__file__).resolve().parents[3] / "tools" / "persona-lora-train"
if str(_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOL_DIR))
