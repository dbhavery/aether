# 02 — Product Family

Three distinct but related products under the **Aether** umbrella. Each has its own planning track, its own codebase boundary (TBD in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md)), and its own cut line.

---

## Umbrella: Aether

Aether is the master platform family for a multimodal AI assistant centered on:
- conversational interaction
- local-first responsiveness
- customizable identity
- high-trust user experience

The umbrella name holds both the open-source community product and the premium flagship. Alternative umbrella names if Aether is dropped: Astrae, Vesper, Eidolon, Lumen, Serein, Auralis.

---

## 1. Aether OSS Preview (free, open-source)

### Role
Free, open-source, launch-fast preview and showcase product. Wedge for adoption, visibility, and community.

### Scope
- Desktop-first
- Text chat (primary mode)
- Mic input (optional)
- Voice output (optional)
- Headshot / bust-level avatar with real-time lip-sync
- Onboarding wizard with info-explainers
- T&S and disclosures
- Simplified permissions (least-privilege presets)
- Performance tier recommendation
- First-run tutorial / checklist
- Teaser surfaces for future features (future-roadmap views, locked modes)

### Policy
- Uses **open-source / available-now components aggressively** — MuseTalk, TalkingHead, Wav2Lip-style refs, Whisper/Parakeet/Distil-Whisper STT, open TTS, Tauri shell, etc.
- Distribution-friendly, contributor-friendly packaging.
- Updates optional / opt-in favored (critical security updates excepted).
- Release channels: stable + experimental; beta if volume justifies it.

### Primary users
- Open-source community and early adopters
- Design-forward early adopters
- Curious mainstream users sampling the concept
- Future contributors / testers / evangelists

### What it is NOT
- Not the flagship.
- Not a placeholder for Pro's missing features.
- Not a polished demo without trust/permissions (those are first-class even here).

### Success profile
Install easy; non-technical users complete onboarding confidently; interact with believable assistant presence; understand what is and isn't permitted; leave with a strong sense the flagship is being built to a serious quality bar.

### Working name
Aether OSS Preview (may shorten to Aether OSS or Aether Preview).

---

## 2. Aether Pro (public flagship, commercial)

### Role
Full-performance public flagship platform. Commercial-grade multimodal assistant with advanced memory, permissions, avatar, multi-device continuity.

### Scope (target end-state)
- Desktop + mobile continuity
- Richer avatar system (photoreal target)
- Advanced multimodal memory
- Text chat + mic + full voice + avatar modes
- Tool use and research (browser, files, email, system, etc.)
- Local/remote model router with latency-aware escalation
- Full performance tiers (Lite / Balanced / Full)
- Downloadable model/asset packs
- Strong permission and autonomy system
- Trust center with action logs and audits
- Red-team readiness built in

### Policy
- **We write our own software from here on.** Primarily custom-built.
- Borrowed primitives only where they don't cap the ceiling or become the moat — and only behind our own interfaces.
- Updates recommended-on by default; mandatory only for critical security/compatibility/trust fixes.
- Release channels: stable + beta + experimental.
- Premium trust posture; survives red-team review.

### What it is NOT
- Not a wrapper around off-the-shelf SaaS.
- Not a superset of OSS Preview — it is a separate architecture that shares identity, onboarding patterns, and trust design principles but not the shortcut stack.
- Not blocked by OSS Preview's constraints.

### Success profile
Clearly not a wrapper product; core user-relationship layers are custom-controlled; feels premium and socially coherent under real use; trust and permissions are legible and auditable; hardware adaptation scales from mainstream to high-performance without losing core identity.

### Working names
Aether Pro, Aether Core, Aether One. [OPEN — see OPEN_QUESTIONS.md]

---

## 3. Isabelle / Isabelle_Kunstig (private personal branch)

### Role
Private customized profile/branch on top of Aether Pro. Personal assistant/companion instance for Don.

### Architecture recommendation
**Isabelle is a privileged profile / branch / configuration super-layer on top of the Aether Pro platform — not a completely separate foundational codebase.**

Rationale: separate codebase = maintenance drag. One shared platform with a private "god-tier profile" layer only Don can access = sustainable.

### Scope (private extensions on top of Pro)
- Custom persona (identity, tone, relationship style)
- Custom appearance (avatar pack)
- Custom voice
- Private memory tuning (salience, retention, provenance rules)
- Private permissions (wider autonomy, private domain/folder allowlists)
- Private workflows (Don-specific automations, integrations, triggers)
- Private-only features intentionally excluded from public distribution
- Tight integration with Don's existing systems (Isabelle_Kunstig data, Tailscale network, existing project tooling)

### Policy
- Not distributed publicly.
- Built on Aether Pro; does not diverge at the platform layer.
- All Pro doctrine applies; Isabelle is strictly additive on top.

### What it is NOT
- Not a parallel codebase.
- Not the free version's personal skin — it's the companion-grade instance.

### Success profile
Isabelle feels like Don's companion — not a generic assistant with a different name. The customization reaches voice, appearance, memory emphasis, workflows, and relationship style without forking the platform.

### Working names
Isabelle / Isabelle_Kunstig. [OPEN — which becomes formal]

---

## Brand hierarchy summary

| Tier | Working name | Role |
|------|--------------|------|
| Umbrella | **Aether** | Product family / master brand |
| Free public | **Aether OSS Preview** | Open-source wedge, community launch |
| Paid public | **Aether Pro** (or Core / One) | Flagship commercial platform |
| Private | **Isabelle** / **Isabelle_Kunstig** | Don's personal companion instance |

Public-facing names for related Don projects (memory-index reference):
- Aether (Isabelle), Vault (Library), Forge (CIGE), Herald (Morning Intel), VoxType (VoiceType), FuelFleet (StaFull).

---

## Separation rules

- **Planning tracks are separate** — each product has its own roadmap in `roadmaps/`.
- **Cut lines are separate** — MVP scope for OSS Preview does not bleed into Pro milestone cut line.
- **Shared concerns** (onboarding patterns, permission architecture, trust UX, design language) may be carried across products, but are defined once in the cross-cutting spec files (`04`–`16`).
- **Isabelle does not drive the public product** — her private needs cannot compromise public product design.

---

## Cross-references
- Doctrine: [01_product_doctrine.md](01_product_doctrine.md)
- OSS Preview roadmap: [roadmaps/aether_oss_preview.md](roadmaps/aether_oss_preview.md)
- Pro roadmap: [roadmaps/aether_pro.md](roadmaps/aether_pro.md)
- Isabelle roadmap: [roadmaps/isabelle_private.md](roadmaps/isabelle_private.md)
- Naming decisions: [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md#naming)
