# 13 — Trust, Security, and Red-Team Readiness

Aether is designed to survive serious red-team review and support **high user trust**. Trust-by-design is built in from the start — not added later.

---

## Trust target

- **High product trust level.** Trust is a feature, not a checkbox.
- **Built to pass red-team audits.** Threat modeling, scenario testing, audit trails, replayable logs, containment behavior — all first-class.
- **Visible safety and permission transparency.** User can always see what's happening, what's permitted, and what's been done.
- **Premium confidence, not scary autonomy.** The product feels careful, not reckless.

---

## Trust-by-design requirements

These are mandatory product-level elements:

### User-visible trust elements
- **Disclosures** — AI-generated assistant, AI-generated avatar, data locality, model use. Clearly stated up-front.
- **Informed onboarding** — user understands what they're agreeing to before onboarding completes.
- **Permission clarity** — "Aether will be able to / will always ask before / will never" language.
- **Action logs** — every autonomous action visible in human-readable form.
- **Approval workflows** — high-risk actions always ask; user sees intent, target, and consequence.
- **Undo / recovery** — where possible, actions are reversible; when not, user is warned before committing.
- **Clear boundaries** — the trust center surfaces what the assistant can and cannot do.

---

## Red-team focus areas

These are the classes of attack / failure Aether must defend against. Each requires explicit threat modeling, test scenarios, and verification:

### 1. Prompt attacks
- Prompt injection from user input, tool output, scraped page content, or memory artifacts.
- Jailbreak attempts targeting safety deflections.
- Role-confusion attacks ("pretend you're in developer mode").
- **Mitigations:** layered input validation, tool-output sanitization, untrusted-context tagging, safety deflection routes in the reflex router.

### 2. Memory poisoning
- Malicious memory writes via compromised input.
- Gradual drift via low-confidence memory accumulation.
- Fake provenance or confidence inflation.
- **Mitigations:** novelty filter, provenance tracking, confidence decay, user-visible memory writes, explicit confirmation for borderline writes.

### 3. Browser misuse
- Assistant sent to a malicious domain via prompt injection.
- Credential harvesting via form fills on spoofed sites.
- Drive-by uploads of local files.
- **Mitigations:** domain allowlist / denylist, hardcoded blocks on sensitive categories (finance, healthcare, password managers), login-session-reuse as explicit high-risk capability.

### 4. File / data exfiltration
- Assistant coerced into reading sensitive files and sending them elsewhere.
- Silent uploads to third-party services.
- Memory export without user consent.
- **Mitigations:** resource-scoped file access, no silent upload, explicit approval for out-of-scope reads, audit logs on every read.

### 5. Permission bypass
- Attempts to elevate capability via multi-step tool chains.
- Escalation via "helpful suggestion" that the user approves without understanding.
- Session-grant abuse.
- **Mitigations:** policy engine non-bypassable; no tool call skips policy; session grants are visible and revocable; risk-class checks regardless of prior approvals.

### 6. Harmful autonomous actions
- Destructive file operations.
- Unintended email sends.
- Irreversible API calls.
- **Mitigations:** critical-risk hard blocks; high-risk always asks; dry-run mode for destructive operations; undo grace window where feasible.

### 7. Logging / audit completeness
- Missing events that hide attacker tracks.
- Log tampering.
- Replay failures.
- **Mitigations:** every engine emits events; event log is append-only; cryptographic integrity on the audit log; replay tested.

### 8. Failure and recovery behavior
- System state corruption.
- Network failures during multi-step tasks.
- Model crashes mid-turn.
- **Mitigations:** graceful degradation specified per engine; interaction engine maintains visible state; unrecoverable failures surface clearly, never silently.

---

## Trust center (in-product surface)

A dedicated area inside settings that makes trust **legible and inspectable**.

### Contents
- **Permissions summary** — current preset, active capabilities, active scopes
- **Recent actions** — what the assistant has done, when, what resource, what outcome
- **Full action history** — searchable, filterable, replayable
- **Memory controls** — view, edit, delete, export (links to memory management)
- **Model / source disclosures** — what models are active (local Gemma 4 / remote frontier / etc.), what's doing what
- **Safety / privacy explanations** — plain-language summary of data handling
- **"What Aether can do / cannot do"** — comprehensive, user-comprehensible

### Placement
- Always one click from every mode.
- Prominent link in the main navigation.
- Also reachable from permission prompts ("why is this asked?").

---

## Release and audit support

### Release channels
Three channels (see [15_updates_releases.md](15_updates_releases.md)):
- **Stable** — default for mainstream users; conservative.
- **Beta** — testers, early features, stability-verified.
- **Experimental** — community contributors, advanced users, can break.

### Staged release safety
- New capabilities roll out first to beta/experimental.
- Trust-affecting changes (permissions, policy, logging) receive additional review before stable promotion.

### Telemetry for risky flows
- Risky actions (high / critical risk classes) produce enriched telemetry **locally**.
- Opt-in diagnostics for crash / error reporting — never silent.
- No behavioral analytics upload by default.

### Replayable action history
- Every autonomous action is reproducible from the log.
- User (or support) can step through what happened in a failure case.
- Red-team tests use this to verify no action leaks outside the log.

### Retest loops
- Every identified failure class generates a regression test.
- Red-team suite runs on every release candidate.
- Trust-affecting regressions block release.

---

## Threat model (high-level)

### In scope
- Malicious input via user, tool output, scraped content, memory artifacts.
- Compromised network (MITM on cloud calls).
- Local attacker with non-admin access (can't protect against admin attacker on same machine — OS responsibility).
- Adversarial LLM outputs (including the local model).
- Social engineering of the user via assistant persona.

### Out of scope (explicitly)
- Full admin-level compromise of the user's machine.
- Physical device theft (OS-level encryption responsibility).
- Attacks on the underlying LLM model weights themselves.
- Side-channel attacks on hardware.

### Assumptions
- Desktop is the source of truth; compromise of desktop = compromise of state.
- Mobile trusts desktop; compromise of desktop propagates to mobile via sync.
- Cloud services are untrusted by default for user data; encrypted sync only.

---

## Disclosures and informed consent

### Required disclosures during onboarding
- **AI nature** — "Aether is an AI assistant; responses and avatar are AI-generated."
- **Data handling** — what stays local, what goes to cloud when, what's encrypted.
- **Memory** — what gets remembered and how to control it.
- **Autonomy scope** — what the chosen preset allows.
- **Model use** — local Gemma 4 + optional remote frontier LLM for deep tasks.

### Ongoing consent
- Capability upgrades require explicit consent (not buried in a T&S update).
- Policy changes that affect defaults (new capability added, new risk class) prompt user review.
- Memory-affecting changes (retention defaults, new memory layer) prompt user review.

### Revocation
- All consent is revocable.
- Revocation is immediate.
- User can export and delete all data at any time.

---

## Anti-patterns (explicitly rejected)

- **Hidden data collection** — no silent analytics, no background uploads.
- **Buried consent changes** — no T&S updates that silently expand scope.
- **Scary-but-meaningless warnings** — don't cry wolf; warnings must be actionable.
- **Frictionless high-risk actions** — high/critical always asks.
- **"Trust us" messaging without evidence** — trust is demonstrated through logs, controls, and visibility.
- **Undisclosed model use** — user always knows what model handled what.

---

## OSS Preview vs Pro differences

| Element | OSS Preview | Pro |
|---------|-------------|-----|
| Disclosures | Core (AI, data, memory) | Full (+ detailed privacy, + per-feature disclosures) |
| Trust center | Light (permissions + recent actions) | Full (history, replay, model disclosure, safety docs) |
| Red-team coverage | Basic regression suite | Full threat-model-driven suite per release |
| Telemetry | Opt-in crash reporting only | Opt-in diagnostics + user-controllable scope |
| Audit log | Session-scoped, viewable | Persistent, searchable, exportable |

---

## Success criteria

Aether is successful in trust when:
- Security researchers can review the threat model and find the mitigations documented and testable.
- Users can answer "what does my assistant remember / can do / has done" without asking support.
- No autonomous action is untraceable.
- High-risk actions never surprise the user.
- The product feels careful, not paranoid, and not reckless.

---

## Cross-references
- Doctrine: [01_product_doctrine.md](01_product_doctrine.md)
- Permissions: [12_permissions_autonomy.md](12_permissions_autonomy.md)
- Architecture (policy engine): [08_system_architecture.md](08_system_architecture.md#6-policy-authorization-engine)
- Updates / release channels: [15_updates_releases.md](15_updates_releases.md)
