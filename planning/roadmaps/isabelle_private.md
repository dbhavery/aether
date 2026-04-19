# Isabelle / Isabelle_Kunstig — Private Branch Specification

## Role

Isabelle is Don's **private personal assistant/companion** — a customized profile/branch built on top of Aether Pro. This is not a separate product and not a separate codebase. It is a **privileged profile layer** on the Aether Pro platform.

---

## Architecture decision

**Isabelle is a privileged profile / branch / configuration super-layer on top of the Aether Pro platform — not a completely separate foundational codebase.**

### Rationale
A separate codebase would create maintenance drag:
- Platform bugfixes have to land in two places
- Moat layers (presence, memory, router, policy, persona, timing, trust) would duplicate or diverge
- Every architectural improvement would cost twice

### The pattern
**One shared platform (Aether Pro) + a private "god-tier profile" layer only Don can access.**

- Isabelle inherits the full Aether Pro runtime.
- Isabelle adds custom persona packs, voice packs, avatar appearance packs, memory configurations, permission presets, integrations, and workflows.
- Isabelle-specific features live in a private overlay, not as forks of platform code.
- Private features are intentionally excluded from public distribution.

---

## Scope (private extensions on top of Pro)

### Persona
- Custom identity and personality tuning
- Custom tone, style, relationship modes
- Private acknowledgment phrase pool variations
- Private persona compiler overrides

### Appearance
- Custom avatar appearance (Isabelle-specific model/rig)
- Personal voice pack (Isabelle-specific TTS model or fine-tune)
- Visual identity not used in public product

### Memory
- **Wider memory ingestion scope** — Don's workflows, projects, personal data, preferences, work history
- **Longer retention** — durable across years, not months
- **Cross-project memory linkage** — Isabelle knows about Don's other projects (Library, CIGE, Portfolio, Morning Intel, VoiceType, Masters Degree, etc.)
- **Private memory categories** not available in public product
- **Integration with existing Isabelle_Kunstig data** where migration from old system applies

### Permissions
- Wider autonomy presets (Don grants more than mainstream users would)
- Custom resource scopes (Don's specific folders, domains, inboxes)
- Private domain allowlists (including Tailscale network 100.105.108.18, I: drive)
- Custom approval thresholds

### Workflows
- Don-specific automations
- Cross-project triggers (e.g., Isabelle knows when VoiceType is active — the `voicetype.active` lockfile rule)
- Integration with existing project tooling
- Integration with Don's Claude Code workflow / skills / agents

### Integrations
- Tailscale network (local private network)
- I: drive for data storage
- Existing project repositories
- Samsung Galaxy S24 companion
- Existing Google Workspace / Gmail / Calendar (per gws tooling)
- Existing course materials / Masters Degree tooling
- LinkedIn / Morning Intel automation awareness

### Private-only features (intentionally excluded from public)
- Any deeply personal memory categories
- Advanced cross-project synthesis
- Private developer / builder features Don wants but mainstream users don't need
- Wider autonomy presets not considered safe for general distribution

---

## Policy

- **Not distributed publicly.** Private only.
- **Built on Aether Pro.** Does not diverge at the platform layer.
- **All Aether Pro doctrine applies.** Isabelle is strictly additive on top.
- **Private overlay structure** — Isabelle configurations, models, and packs live separately from the public Pro codebase.
- **Memory / data isolation** — Isabelle's memory database is never accessed by public product code paths.

---

## Memory migration (from existing Isabelle_Kunstig)

### Source data
- `file:///C:/Users/dbhav/Projects/Isabelle_Kunstig/`
- LoRA v2.0 training data (81 imgs, 13 AI sources, 2500 steps — per memory index)
- Existing persona / config / logs / reports
- Existing interview docs
- Existing research documents
- Any durable memory artifacts from the old system

### Migration strategy (to be refined)
- **Do not auto-import.** Migration is manual / curated.
- Review each category for relevance to new Isabelle.
- Structured import into Aether Pro memory engine (with proper provenance, confidence, and governance).
- Old Isabelle_Kunstig data preserved read-only during migration.
- Migration tooling lives in Pro's offline tooling layer (Python OK for this — non-runtime).

See [../OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md#architecture-decisions-deferred) for deferred decisions.

---

## Personal context Isabelle inherits (from memory index)

These are facts about Don that Isabelle should carry forward as durable memory from day one:

- Windows 11, bash shell, Samsung Galaxy S24
- Tailscale 100.105.108.18
- I: drive for data storage
- Deep 3D neumorphic monochrome UI aesthetic preference
- Direct communication, no fluff — Don directs, AI agents build
- Active projects: Isabelle_Kunstig, CIGE, Library, Morning Intel, Masters Degree, VoiceType, Portfolio
- Public product naming convention: Aether (Isabelle), Vault (Library), Forge (CIGE), Herald (Morning Intel), VoxType (VoiceType), FuelFleet (StaFull)
- Coordination pattern with 2-agent Isabelle work (see [project_two_agent_coordination.md])
- Don's locked behavioral feedback rules (CSS/HTML for UI, no CSS mockups for showcases, clickable file links, don't ask — just execute, self-review loop, etc.)

This is personal context that makes Isabelle feel like Don's assistant from session one — not something to discover over months.

---

## Tech stack

**Identical to Aether Pro** — Isabelle is a profile layer, not a separate stack.

- Desktop shell: Tauri + TypeScript/React
- Runtime: Rust
- Local LLM: Gemma 4 (Full variant given Don's hardware class)
- Remote LLM: frontier for hardest tasks (scoped)
- All moat layers: the Pro custom implementations
- Memory: SQLite + vector, encrypted, with Isabelle-specific schema extensions
- Avatar: Pro rendering surface with Isabelle-specific appearance pack

See [../16_tech_stack.md](../16_tech_stack.md).

---

## Private deployment

### Where Isabelle runs
- Don's primary desktop (full tier, larger Gemma 4 variant)
- Samsung Galaxy S24 companion (when mobile shell is ready)
- Tailscale-connected private network between devices

### Private build
- Private build pipeline (not part of public release channels)
- Private updates (not on public release cadence)
- Isabelle-specific configurations not committed to public repos

### Public/private separation (memory rule)
- [No personal data in public repos](file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_no_personal_data_public.md)
- [Public vs private naming](file:///C:/Users/dbhav/.claude/projects/C--Users-dbhav-Projects/memory/feedback_public_private_naming.md)
- Isabelle's private repo / overlay is strictly separated from the public Aether repos

---

## Integration with Don's existing workflow

### Don's Claude Code setup
- Isabelle should be aware of Don's Claude Code skills, agents, and workflows
- Isabelle can hand work to Claude Code for development tasks (future capability)
- Isabelle and Claude Code coexist — Isabelle is the companion, Claude Code is the agent harness

### Don's other AI-agent products (memory-referenced)
- **Morning Intel** — LIVE 2026-03-20, 6 AM daily LinkedIn automation
- **VoiceType** — Push-to-talk dictation (right-ctrl); its lockfile must mute Isabelle
- **CIGE** — image generation/editing, separate product
- **Library / Vault** — self-hosted data server
- Isabelle should be aware of and coexist with these, not replace them

### Coordination
- Isabelle should not fight with VoiceType (`voicetype.active` lockfile mutes Isabelle)
- Isabelle should not interfere with Morning Intel's 6 AM automation
- Isabelle should be aware of Claude Code sessions in progress

---

## Roadmap (follows Aether Pro)

Isabelle's roadmap depends on Aether Pro reaching each phase:

- **Pro Phase 0–1 (platform core)** → Isabelle preparation: persona pack spec, appearance pack spec, migration plan for Isabelle_Kunstig data
- **Pro Phase 2 (conversation core)** → Isabelle alpha: basic persona + voice + memory on Don's desktop
- **Pro Phase 3 (avatar)** → Isabelle avatar: custom appearance pack integrated
- **Pro Phase 4 (tools/autonomy)** → Isabelle autonomy: wider permissions, private integrations
- **Pro Phase 5 (memory/continuity)** → Isabelle memory migration from old Isabelle_Kunstig + mobile companion
- **Pro Phase 6 (companion quality)** → Isabelle becomes the full companion

Isabelle does not race ahead of Pro. Pro's stability is Isabelle's stability.

---

## Naming

- **Working name:** Isabelle / Isabelle_Kunstig
- **Public reference from memory:** "Aether (Isabelle)" — Aether is the public product family; Isabelle is the private instance
- **Decision on formal name** in [../OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md#naming)

---

## Success criteria

Isabelle is successful when:
1. She feels like **Don's companion** — not a generic assistant with a different name.
2. Customization reaches voice, appearance, memory, workflows, and relationship style.
3. **No platform fork exists** — Isabelle rides on Aether Pro.
4. Memory migration from old Isabelle_Kunstig preserves what matters and discards noise.
5. Isabelle coexists with VoiceType, Morning Intel, Claude Code, and other Don tooling without conflict.
6. Private features stay private; public repos stay clean.
7. Isabelle benefits from every Pro improvement automatically.

---

## Anti-patterns (explicitly rejected)

- **Separate codebase for Isabelle** — creates maintenance drag, duplicates moat layers
- **Public leakage of private Isabelle data** — never in public repos
- **Isabelle-first development that branches the platform** — Pro must be the canonical source
- **Auto-import of all old Isabelle_Kunstig data** — curated migration only
- **Wider autonomy without wider logging** — Don's trust center still shows everything
- **Isabelle models in public model packs** — private models stay in private distribution

---

## Cross-references
- Doctrine: [../01_product_doctrine.md](../01_product_doctrine.md)
- Product family (Isabelle's place): [../02_product_family.md](../02_product_family.md#3-isabelle--isabelle_kunstig-private-personal-branch)
- Memory architecture (Isabelle extensions): [../10_memory_architecture.md](../10_memory_architecture.md#isabelle-specific-memory)
- Tech stack: [../16_tech_stack.md](../16_tech_stack.md#isabelle-stack-notes)
- Aether Pro roadmap (Isabelle rides on): [aether_pro.md](aether_pro.md)
- Open questions: [../OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md)
