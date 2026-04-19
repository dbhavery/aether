# 15 — Updates & Release Management

Aether's update policy and release channels. Updates are **mostly optional**, mandatory only for critical security / compatibility / trust issues.

---

## Update policy

### General rule
Updates should be **mostly optional or recommended**, not universally forced.

### Mandatory update exceptions
Forced updates are reserved for:
- **Critical security fixes**
- **Breaking compatibility issues** (older version can no longer function correctly)
- **Trust-related defects** (permission bypass, audit log failure, policy engine regression)

Outside these cases, the user decides when to update.

---

## OSS Preview update stance

- **Optional / opt-in favored.**
- Community-friendly — contributors and experimenters can stay on their chosen version.
- Low-friction installation and experimentation.
- Critical security updates are the only mandatory class.
- Update notifications are non-nagging and respect user intent.

Rationale: open-source communities dislike forced updates. Aggressive update pushes alienate the audience Aether OSS is trying to reach.

---

## Pro update stance

- **Recommended-on by default**, but respectful.
- Auto-update opt-in during onboarding; clear toggle in settings.
- Critical updates forced (as defined above).
- Non-critical updates: notify the user, offer to update, let them choose.
- Security-patch-only auto-update mode available for cautious users.

Rationale: paid commercial product users benefit from defaults that keep them safe, but still respect autonomy.

---

## Release channels

### Stable
- Default channel for mainstream users.
- Conservative — only well-tested builds.
- Prioritizes reliability over novelty.
- Trust-affecting changes receive additional review before promotion.

### Beta
- Testers, early access users, paid Pro subscribers who opt in.
- Stability-verified but newer features.
- Bugs expected but not destabilizing.

### Experimental
- Community contributors, advanced users, internal development.
- Can break.
- Used to validate new capabilities before beta promotion.
- Explicit opt-in required; clear "this is experimental" labeling.

### Channel switching
- Users can switch channels at any time.
- Channel switching is surfaced in Settings → Updates.
- Downgrade handled gracefully (may require a clean reinstall in edge cases; warned clearly).

---

## Update UX

### Notification pattern
- **Non-blocking** — updates never stop the user mid-task.
- **Informative** — changelog shown in-product, not just "update available."
- **Respectful** — no repeated nagging; one notification, then dismissable.
- **Searchable** — past changelogs accessible from settings.

### Update timing
- Updates download in background (when user allows).
- Apply on next launch — never during active session.
- Exception: critical security patches may apply immediately with user confirmation.

### Update failure handling
- Rollback on failed update.
- Previous version preserved during install.
- User notified clearly if rollback occurs.

---

## Versioning

### Semantic versioning
- **Major** — significant feature changes, potentially breaking.
- **Minor** — new features, backwards compatible.
- **Patch** — fixes, security patches.
- Users see the version clearly in the trust center and settings.

### Per-component versioning
- Core app, model packs, asset packs, voice packs can update independently.
- Each pack has its own version.
- Pack updates respect the same optional / mandatory classification.

### Deprecation policy
- Features deprecated with clear warnings N versions ahead.
- Deprecated features continue working during the grace period.
- Removal only after user notification and alternative available.

---

## Cross-channel promotion

New capabilities flow:
1. **Experimental** — first build, labeled experimental, community-testable.
2. **Beta** — after stability verification.
3. **Stable** — after broader testing and trust review.

Trust-affecting changes (permission model, policy engine, logging, disclosures) require **additional review** at each promotion step.

---

## Integration with trust center

Update-related trust elements:
- Current version visible
- Current channel visible
- Recent updates listed with changelog links
- "What changed in this update" summary for each installed update
- Model / pack versions disclosed separately

---

## Anti-patterns (rejected)

- **Silent forced updates** — violates user autonomy.
- **Update-as-punishment** — no "can't use app until you update" screens except for critical security cases.
- **Buried changelogs** — always in-product and readable.
- **Auto-opt-in to beta / experimental** — always explicit opt-in.
- **Permanently breaking older versions** — deprecation grace period required.
- **Telemetry-tied update gating** — updates don't depend on analytics opt-in.

---

## OSS Preview vs Pro differences

| Element | OSS Preview | Pro |
|---------|-------------|-----|
| Auto-update default | Off / opt-in | On / opt-out during onboarding |
| Update notification style | Passive | Passive but more visible |
| Critical update enforcement | Yes (security only) | Yes (security + compatibility + trust) |
| Channels available | Stable + Experimental | Stable + Beta + Experimental |
| Changelog surface | In-product + GitHub release notes | In-product detailed |
| Rollback UX | Manual reinstall | In-product rollback |

---

## Cross-references
- Trust / audit: [13_trust_security_redteam.md](13_trust_security_redteam.md)
- OSS Preview distribution: [roadmaps/aether_oss_preview.md](roadmaps/aether_oss_preview.md)
- Pro release process: [roadmaps/aether_pro.md](roadmaps/aether_pro.md)
