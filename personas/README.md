# Persona Packs

This directory holds the bundled persona packs that ship with Companion v1.0. Each persona is a self-contained folder defining one character's look, voice, and personality.

**Canonical schema:** see [../docs/PERSONA-SCHEMA.md](../docs/PERSONA-SCHEMA.md)

---

## Structure

```
personas/
├── README.md                 (this file)
├── _example/                 reference persona showing required structure
│   └── persona.yaml          placeholder schema example
├── aurora/                   to be generated in P4
├── caelum/
├── luma/
├── rhea/
├── kai/
├── nova/
├── onyx/
├── sage/
├── milo/
├── ivy/
├── atlas/
└── wren/
```

All 12 personas will be populated in **P4 — Persona pack pipeline**. Each requires:

- AI-generated portrait + 4 state images
- Generated idle clips (machine-derived from portraits, not committed to git)
- Voice reference from a royalty-free source (CC0)
- Written personality prompt (hand-authored, not LLM-generated)
- Complete `metadata.yaml` with license audit

---

## Adding a new persona

Create the persona folder following the canonical structure (see
PERSONA-SCHEMA.md). Each new pack must match the existing folder
layout and ship a complete `metadata.yaml` with a license audit.

---

## Licensing

Every persona pack must pass `scripts/audit_persona.py <id>` before merging to `dev`. The audit verifies:

- `metadata.yaml` exists and is complete.
- Every asset's source is documented.
- No assets claim sources we can't verify.
- Commercial-use rights are clean for all assets.

Users' custom personas live in `%APPDATA%/aether/personas/` and are not subject to this audit — that's their problem. But anything we ship must be clean.

---

## User-created personas

Users can create their own personas at runtime via Sandbox → Personas → Create New. The app generates a pack in `%APPDATA%/aether/personas/<user_id>/` with the same structure as a bundled pack. If a user-created persona has the same `id` as a bundled one, the user version takes precedence (this is how users "edit" a bundled persona — they copy it and modify the copy).

---

## `_example/` folder

Ships with v1.0 as a reference. Shows the full folder structure and a skeleton `persona.yaml` with inline comments. Not selectable in the wizard — filtered out by the loader because its `id` starts with `_`.

Purpose: makes the pack format obvious for anyone who wants to contribute a persona in the future.
