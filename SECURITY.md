# Security Policy

Free Aether — Community Edition is an early-preview, local-first architecture project. Security of the policy gate, the audit log, and the local data boundary is load-bearing to the product vision, so security reports are welcome and taken seriously even at this stage.

## Scope

The following are considered in-scope for security reports:

- **Policy bypass.** Any path that executes a side-effectful action (file I/O, network, subprocess, tool execution) without going through `packages/l5-policy`.
- **Audit log tampering.** Any path that can insert, modify, or delete entries in `policy_audit_log` without the configured hash-chain + HMAC contract once Wave 4.x lands. For Wave 3.5, the append-only SQL triggers are the baseline guarantee.
- **Capability confusion.** Any case where a call that should require a specific capability is evaluated against the wrong capability, or where grant matching accepts a resource scope outside the grant.
- **BYOK / credential leakage.** Any path that exposes a user-supplied API key, token, or secret in logs, telemetry, error messages, crash reports, or persisted artifacts.
- **Persona privilege escalation.** Any path that lets a non-privileged persona run with the rights of a privileged persona (for example, acquiring Isabelle-tagged capability without the configured precondition).
- **Cross-layer import violation.** Any supply-chain path that bypasses the seven-layer boundary rules enforced in `tools/lint-layer-boundaries/` in a way that creates a real vulnerability — not merely a lint-rule miss.

Out of scope for this preview:

- Denial-of-service from adversarial input on an offline local binary (the product has no public surface yet).
- Issues that depend on the operator running a modified build with guardrails disabled.
- Theoretical issues in the legacy v1.0 Python tree (`src/`, `desktop/`, `frontend/`, `configs/`, `personas/`, `scripts/`, `tests/`). That tree is frozen and being ported out; please flag those as ordinary issues rather than security reports.

## Supported versions

Only the current `dev` branch is supported for security updates during the preview. There is no tagged release yet. Once the first tagged preview ships, this section will be updated to list the supported tags.

## Reporting a vulnerability

Please report suspected vulnerabilities **privately**. Do **not** open a public GitHub issue for a security report.

Preferred channel:

- **GitHub private vulnerability reporting.** On this repository, use "Security" → "Advisories" → "Report a vulnerability." This opens a private advisory visible only to the maintainer.

Fallback channel:

- DM `@dbhavery` on GitHub. Include a minimal reproducer, the affected commit SHA, and a plain description. Do not include sensitive credentials in a DM; describe them instead and we will arrange a private channel.

### What to include

- A short description of the issue and impact.
- A commit SHA (or tag, once releases exist) where the issue is present.
- Steps to reproduce, including OS, Rust toolchain version (`rustc --version`), and any non-default config.
- Affected layer or package (`packages/l5-policy/`, `packages/storage/`, etc.).
- Optional: suggested fix direction.

## Disclosure process

1. Maintainer acknowledges receipt within 7 days (the preview is maintained by a single person; slack is intentional).
2. Severity is triaged against the in-scope list above.
3. For in-scope issues, a fix is prepared on a private branch. For infrastructure/config issues, the fix may land on `dev` directly if public exposure is minimal.
4. Once a fix is merged and (if applicable) a preview tag cut, a GitHub Security Advisory is published with a plain description and credit (with the reporter's consent).
5. If the reporter prefers anonymity, the advisory will not name them.

The project does not currently run a paid bug bounty. Credit in the advisory is the acknowledgment we can offer today.

## Safe-harbor

Security research conducted in good faith against this repository — including running the local binary, exercising the policy gate with unusual input, and reporting findings through the channels above — will not result in legal action from the project. This does not grant permission to test against third-party systems or services that Aether integrates with; please respect those services' own policies.
