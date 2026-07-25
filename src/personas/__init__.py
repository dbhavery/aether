"""Persona pack subsystem — loader, validator, runtime manager.

See `docs/PERSONA-SCHEMA.md` for the canonical schema and
`docs/ARCHITECTURE-V2.md` §4.7 for runtime expectations.
"""

from src.personas.manager import PersonaManager, get_persona_manager
from src.personas.models import PersonaManifest

__all__ = [
    "PersonaManager",
    "PersonaManifest",
    "get_persona_manager",
]
