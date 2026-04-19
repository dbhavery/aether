# 12 — Permissions & Autonomy

The capability-based permission model. This is a **must-own custom-built moat layer** — the product's trust surface depends entirely on it.

---

## Core requirement

The assistant must support **multiple levels of automated control** — configurable in onboarding and settings, understandable to non-technical users. This is central to high-trust product design, not an afterthought.

Treat permissions as **capabilities**, not simple app-access toggles. "Browser access" is not one permission — it is a family of permissions (read page, navigate, extract data, fill forms, upload, download, submit actions, reuse login sessions).

---

## Philosophy

- **Default deny** — nothing is implicitly allowed.
- **Least privilege** — grant the minimum capability needed for the task.
- **Capability-based access** — not role-based, not app-based, capability-based.
- **Resource scoped** — capabilities apply to specific folders / domains / inboxes, not the entire system.
- **Time-limited grants** — per-action, per-task, per-session, or persistent — user-chosen.
- **Full logging and review** — every autonomous action recorded.
- **Reversible** — grants can be revoked instantly; actions undone where possible.

---

## The five permission layers

Each capability is evaluated across five independent axes:

| Layer | Controls | Example |
|-------|----------|---------|
| **Feature access** | Whether a capability family exists at all | "Browser tools enabled" vs "disabled" |
| **Action scope** | What the assistant may do within that family | "Read pages only" vs "Read + fill forms + submit" |
| **Resource scope** | Which folders / domains / inboxes are in-bounds | "Only `/Aether_Workspace/Projects/`" |
| **Approval mode** | Auto-allowed, asks, or blocked | Auto-read / ask-before-send / never-access-banking |
| **Grant duration** | How long permission lasts | One task / one session / until revoked |

A permission check evaluates all five layers. Any deny at any layer blocks the action.

---

## Capability groups

### Files
- Read files
- Create files
- Edit files
- Rename / move files
- Delete files
- Bulk file operations
- Modes: workspace-only vs selected folders vs full custom folder list

### Browser
- Open approved sites
- Read page content
- Extract structured data
- Fill forms
- Upload files
- Download files
- Click / submit actions
- Login / session reuse
- Domain allowlist / denylist

### Email
- Read inbox metadata (subjects, senders, dates)
- Read email bodies
- Draft emails
- Edit drafts
- Send emails
- Access attachments
- Recipient scope: approved-only / contacts-only / unrestricted

### System & tools
- Read clipboard
- Write clipboard
- Execute scripts
- Run terminal commands
- Install packages
- Read notifications
- Trigger automations / integrations

### Memory & data
- Save conversation memory
- Save extracted preferences
- Save facts from uploaded files
- Use memory in future tasks
- Export memory
- Delete memory (auto after session / after review / manual)

### Media (new in modes context)
- Microphone access
- Camera access (for user attention signal)
- Screen capture (for screen-understanding tasks)

### Integrations (later / Pro)
- Third-party service access (scoped per service)
- External API use
- Automation triggers

---

## User-facing autonomy presets

Most users pick a preset during onboarding. The preset rolls up the capability matrix into a simple choice:

### Observer
- Chat, remember allowed preferences, and read only what the user explicitly provides.
- No autonomous actions.
- Safest default for cautious or first-time users.

### Assistant (default recommendation for most users)
- Can read approved files / pages, draft outputs, and prepare actions.
- **Asks before anything sensitive.**
- Won't send emails, won't submit forms, won't delete files without approval.

### Operator
- Low-risk actions automatically inside approved scopes.
- High-risk actions still require approval.
- Good for users who want the assistant to actually *do* things.

### Power User / Builder
- Expanded local tools, wider folder access, scripting, browser workflows.
- Strong logs and visible warnings.
- Suitable for developers and advanced users.

### Custom
- Full granular capability matrix.
- User defines every axis.

The preset is editable after onboarding from Settings → Permissions.

---

## Risk classes

Every action is tagged with a risk class. Approval behavior defaults per class:

| Class | Examples | Default approval |
|-------|----------|------------------|
| **Low** | Read page, read project file, summarize inbox subjects | Auto-allow within scope |
| **Medium** | Edit local draft, create file, fill form, prepare email | Configurable (preset-dependent) |
| **High** | Send email, delete files, upload data, log into accounts, run terminal commands | Human approval required |
| **Critical** | Purchases, financial actions, security changes, irreversible destructive operations | Hard-blocked unless explicitly enabled in advanced settings + confirmed per action |

---

## Approval patterns

- **Always allow within scope** — auto-execute, logged.
- **Ask every time** — explicit per-action approval UI.
- **Ask once per session / task** — user grants for a bounded scope.
- **Draft only** — prepare the action but don't execute; user reviews and clicks to run.
- **Deny always** — hard block; can only be unblocked from advanced settings.
- **Admin / advanced approval thresholds** — later, for multi-user scenarios (not near-term).

---

## Onboarding integration

Onboarding includes a dedicated **Autonomy & Permissions** step (Step 5 in [06_onboarding_spec.md](06_onboarding_spec.md)).

Surface pattern:
1. **Recommended preset** selected by default (usually "Assistant").
2. Plain-language summary:
   - "Aether will be able to: [list]"
   - "Aether will always ask before: [list]"
   - "Aether will never: [list]"
3. **Resource pickers** for approved folders / domains (optional, conservative defaults).
4. **"Customize"** expansion for the full capability matrix.
5. **Review screen** before onboarding completes.

Rationale: agent trust is formed at setup time. Careful boundaries + reversible controls up front = premium, trustworthy. Hidden-in-settings permissions = scary, distrustful.

---

## Settings integration

After onboarding, permissions live in a dedicated settings area:

- **Preset selector** (switch between presets)
- **Capability matrix** (granular per-capability controls)
- **Resource scope editor** (folder pickers, domain allowlists)
- **Temporary grants view** (active session-scoped permissions + revoke)
- **Action history / audit log** (what has the assistant done?)
- **Emergency revoke all** (big red button)
- **Trust center link** (see [13_trust_security_redteam.md](13_trust_security_redteam.md))

Both **standing permissions** (always-on) and **temporary task grants** (session-bound) are visible, distinct, and revocable.

---

## Non-negotiable blocks (hardcoded platform rules)

These are platform-level constraints that cannot be bypassed by presets or settings except via explicit advanced-mode toggles with clear warnings:

- **No unrestricted full-disk access by default.**
- **No email sending without explicit enablement.**
- **No terminal / package install privileges** in consumer-safe presets.
- **No browser access to finance, healthcare, government, or password-management domains** unless explicitly allowed.
- **No silent file upload to third parties.**
- **All autonomous actions logged** — intent, target, outcome.

These rules survive preset switching. Advanced users can override in Custom, but with explicit per-category confirmation.

---

## The policy engine (implementation)

The policy / authorization engine (one of the six engines in [08_system_architecture.md](08_system_architecture.md)) evaluates every action request.

### Decision inputs
- User role / profile
- Selected preset
- Task intent (what the assistant is trying to do)
- Requested capability
- Target resource
- Risk class
- Approval requirement for this class
- Current session grants
- Audit policy

### Decision outputs
- `allow` — execute, log
- `ask` — surface approval UI, await user, log decision
- `deny` — block, log, notify user
- `needs_upgrade` — capability not enabled at all; ask user if they want to enable (distinct from per-action ask)

### Critical rule
**The assistant never directly calls tools.** Cognition emits `action_request`; the policy engine decides; only then does the action execute. No bypass path.

---

## OSS Preview vs Pro differences

| Feature | OSS Preview | Pro |
|---------|-------------|-----|
| Preset options | Observer + Assistant (simplified) | Full 5-preset ladder + Custom |
| Resource scoping | Workspace-only default; selected folders advanced | Full custom folder / domain scoping |
| Capability coverage | Files (read/draft), Browser (read), Memory, Clipboard, Media | Full capability matrix including Email, Terminal, Integrations |
| Temporary grants | Session-bound only | Full duration ladder (action/task/session/persistent) |
| Audit log | Recent actions view | Full replayable action history |
| Emergency revoke | Yes (basic) | Yes (with per-category granularity) |

---

## Anti-patterns (explicitly rejected)

- **Broad standing permissions** — violates least-privilege doctrine.
- **Hidden permissions UX** — if the user can't see it, they can't trust it.
- **Bundled "agree to everything"** — no dark patterns.
- **Unexplained capability jargon** — every capability has an info explainer.
- **Silent capability escalation** — if a task needs a capability the user hasn't granted, the policy engine asks; it does not escalate silently.
- **Auto-approval of high/critical actions** — never, even in Power User mode.

---

## Cross-references
- Doctrine: [01_product_doctrine.md](01_product_doctrine.md)
- Onboarding step 5: [06_onboarding_spec.md](06_onboarding_spec.md#step-5-permissions-autonomy)
- Policy engine (architecture): [08_system_architecture.md](08_system_architecture.md#6-policy-authorization-engine)
- Trust center / audit: [13_trust_security_redteam.md](13_trust_security_redteam.md)
