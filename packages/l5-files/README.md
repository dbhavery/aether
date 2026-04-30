# aether-l5-files — L5 file-workflow capability surface

> **Status:** Skeleton only. Implementation lands in follow-up PRs per the T1.3 sub-decisions.

This crate is the L5-gated file-workflow surface for Companion. It does not exist as a *new* policy layer; it is the additive set of capabilities that extends `aether_l5_policy::Capability` with file-workflow primitives.

## Scope (frozen 2026-04-30)

`FilesRead` and `FilesCreate` already live on `aether_l5_policy::Capability`. This crate adds the following in follow-up impl PRs:

- `FilesEdit` — modify an existing file in approved scope.
- `FilesDelete` — remove a file. Always Ask in Operator; per-session grant in Power User.
- `FilesMove` — relocate / rename a file. Always Ask in Operator; per-session grant in Power User.
- `FilesArchive` — archive a file (compress / move to archive tree).
- `FilesGrep` — content search across approved scope (read-only).

## Scope model

**Explicit allowlist** (locked T1.3 §5.2). The approved scope is the directory tree the user explicitly granted via the existing approval framework. Matches the `MediaPermissions` shape already in the policy layer. No glob-pattern whitelists; no implicit project-tree expansion.

## Approval mode by autonomy preset

| Preset | Read / Grep | Create / Edit | Delete / Move | Outside scope |
|---|---|---|---|---|
| Observer | Deny | Deny | Deny | Deny |
| Assistant | Ask | Ask | Ask | Deny |
| Operator | Auto (in scope) | Auto (in scope) | Ask | Deny |
| Power User | Auto + per-session grants | Auto + per-session grants | Ask + per-session grants | Per-session grant only |

## Hard rules

- **Outside-scope writes are Deny** in Observer / Assistant / Operator. There is no escalation path in those presets — the user must either grant the directory or switch to Power User.
- **Power User outside-scope grants are per-session only.** They do not persist across app restarts. Persistent allowlists require an explicit `MediaPermissions`-style write through the approval framework.
- **`FilesDelete` and `FilesMove` never go Auto.** Even in Operator inside approved scope, both stay Ask. The cost of an unintended delete or rename is too high to fold into the auto path.
- **No symlink traversal across scope boundaries.** Implementation PRs must canonicalize before authorization checks so a symlink inside scope cannot point outside it.

## What this crate does NOT do

- Implementation. The capability primitives, the executor wiring, the audit-row emission — all land in follow-up PRs. This crate only holds the type space + the doc surface so the workspace check passes.
- New approval modes. `ApprovalScope` ("Ask once per session / task") and "Draft only" land in `aether-l5-policy` directly per T1.3 §2.3.
- File search indexing. `FilesGrep` is a live-scan capability; persistent indexing is a separate later slice.
- Credential / secret-file handling. Out-of-scope for T1.3 (locked §5.4).

## References

- `planning/plans/T1.3_browser_file_workflow_proposal.md` §2.2 — Approved coordinator proposal (status flipped 2026-04-30 under Don's "1–5 are your decisions now" delegation).
- `planning/12_permissions_autonomy.md` — autonomy preset framework + risk classes; §"Power User / Builder" governs the per-session-grant rules above.
- `aether_l5_policy::Capability` — the additive surface where new variants land. `FilesRead` + `FilesCreate` already exist there.
