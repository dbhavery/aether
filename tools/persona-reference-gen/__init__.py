"""tools/persona-reference-gen — structured, reproducible reference image generator.

Per ADR-0015, reference image generation for the public-cast persona pipeline
lives inside the Companion repo (not in CIGE/Forge). This module implements
ADR-0014 Step 1 (Don-curated full-body photoreal reference set).

See:
  docs/adr/ADR-0015-reference-image-generation-inside-companion.md
  docs/adr/ADR-0014-per-persona-character-pipeline.md
  planning/plans/gpu_queue.md

NOTE on import path: this directory uses a hyphen (`persona-reference-gen`)
to match ADR-0015's hard constraint. Python imports therefore go via the
explicit script path or the `__main__.py` entry, not `python -m
tools.persona_reference_gen`. See README.md.
"""

__all__ = [
    "output_schema",
    "prompt_matrix",
    "runner",
]
