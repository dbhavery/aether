"""Module entry: forwards to runner._main.

Allows `python tools/persona-reference-gen/__main__.py ...` and serves as
the canonical CLI entry. Note: this directory is hyphen-named per ADR-0015,
so `python -m tools.persona_reference_gen` does NOT work. Either invoke this
file directly, or add `tools/persona-reference-gen/` to PYTHONPATH and
`python -m runner`.
"""

from __future__ import annotations

from pathlib import Path
import sys

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from runner import _main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(_main())
