# AETHER NEXT-SESSION PLANNING PROMPT

You are continuing planning work for the Aether product family.

## Authority and operating model

Treat this prompt plus the planning folder as the canonical planning context for this session. Do not relitigate locked doctrine unless a contradiction is discovered. Human coordinator authority remains with Don; do not invent policy changes or downgrade product standards without flagging them explicitly. Current agent workflow guidance favors centralized context, explicit authority, and scoped handoffs rather than loosely coordinated autonomous planning. [cite:258][cite:260][cite:264]

## First actions

1. Read the planning folder and the latest handoff file in full before making decisions.
2. Build a short session-start summary:
   - what is already complete,
   - what is locked,
   - what is still open,
   - what files will likely be touched today.
3. Then proceed using the locked decisions below.
4. If a file and this prompt conflict, flag the conflict and preserve both versions rather than silently choosing one.

## Locked doctrine

The following are locked and should be treated as hard planning rules:

1. Aether Pro is not a commodity wrapper product.
2. “Close enough” SaaS is unacceptable in core differentiator layers.
3. Bare-metal or near-bare-metal custom creation is required for strategic moat layers.
4. User experience is the top-priority constraint for the flagship.
5. The long-term target is the highest believable assistant/companion relationship standard.
6. Local-first architecture is preferred wherever it preserves responsiveness, trust, and user control.
7. Shared cross-system foundations should be reused across Aether-family products.
8. Planning should optimize for systems ownership, not short-term convenience.

These rules align with current product and agent-design guidance that recommends keeping differentiators under direct control, centralizing standards, and preserving human oversight over quality-sensitive decisions. [cite:193][cite:194][cite:196][cite:268]

## Locked decisions for this session

### 1) Segmentation axis

Primary planning axis is **per-must-own-layer**.  
Secondary planning view is **per-Pro-phase**.

Interpretation:
- The main plan set should be organized around must-own layers such as interaction timing, memory, presence, routing, policy, persona, and trust UX.
- A second crosswalk should map those layers into phased delivery for Pro.
- Do not use per-product as the primary planning spine.

Reason: the moat lives in the owned layers, and planning should reflect what must be custom-controlled. [cite:193][cite:195][cite:156]

### 2) Desktop framework decision

**Long-term desktop foundation remains Tauri.**  
**pywebview may be used only as a tactical OSS Preview shortcut if speed-to-demo absolutely requires it.**

Interpretation:
- Update planning memory so the strategic platform choice is Tauri.
- Do not rewrite family doctrine around pywebview.
- If you preserve pywebview anywhere, mark it clearly as tactical, preview-only, and non-doctrinal.

Reason: Tauri is better aligned with a Rust-native, lower-overhead, serious desktop foundation. [cite:102][cite:111][cite:251]

### 3) Isabelle migration

**Migration strategy is phased with short parallel overlap, then cutover.**

Interpretation:
- No hard cutover as the baseline recommendation.
- No indefinite parallelism.
- Plan by capability/domain migration with verification gates.

Reason: phased migration reduces risk while preserving continuity and validation. [cite:246][cite:249][cite:252]

### 4) Repo structure

**Target repo strategy is a monorepo with strong internal boundaries.**

Interpretation:
- Consolidate scattered repos into a single source-of-truth structure unless a very strong exception emerges.
- Organize into apps, shared packages, planning/docs, and research/prototypes.
- Preserve ownership and boundaries through structure, not fragmentation.

Reason: shared systems, shared doctrine, and AI-assisted development all benefit from unified context. [cite:242][cite:245][cite:250]

### 5) Prompt format and coordinator

**Use self-contained briefing packs plus task-specific one-shot prompts. Human coordinator remains Don.**

Interpretation:
- Each new agent session should begin from a concise briefing pack.
- Execution prompts should be focused and task-bounded.
- Do not assume a free-running meta-agent is the operating model.
- The human coordinator resolves doctrine and acceptance decisions.

Reason: this project depends on quality ceiling, taste, and doctrine enforcement, not just task completion. [cite:258][cite:260][cite:268]

### 6) Remaining v1.0 unique content

**Yes — port remaining v1.0 unique content that materially affects doctrine, architecture, or segmented planning before final segmented plans are declared complete.**

Priority items:
- 8-screen wizard
- Guest mode
- Distribution playbook
- Cost visibility UX

Interpretation:
- If these are not yet fully represented in planning, extract and port them now.
- If full porting would delay progress too much, create a compact content-lock artifact first, then continue segmented plans.

Reason: planning quality improves when scope-defining product content is stabilized before deeper architecture segmentation. [cite:170][cite:171][cite:174]

## What this session should produce

Produce the next planning package in this order:

### Deliverable 1: Layer-based segmented plans

Create segmented planning docs for the must-own layers, at minimum:
- Interaction timing engine
- Memory kernel
- Presence engine
- Model router
- Policy/authorization engine
- Persona/compiler system
- Trust UX and onboarding system

For each layer, include:
- purpose,
- why it is must-own,
- boundaries,
- dependencies,
- what can be borrowed,
- what must be custom-built,
- key risks,
- sequencing,
- acceptance criteria.

### Deliverable 2: Pro-phase crosswalk

Create a crosswalk that maps each must-own layer into Pro phases.  
This should answer:
- what lands in Phase 0,
- what lands in Phase 1,
- what can wait,
- what blocks later work.

### Deliverable 3: OSS Preview alignment map

Create a concise map showing which portions of each must-own layer appear in OSS Preview, and which remain Pro-only.

### Deliverable 4: Prompt pack

Create copy-paste prompts for future agents:
- one prompt per major planning stream,
- one prompt for repo restructuring planning,
- one prompt for migration planning,
- one prompt for Tauri-first architecture planning,
- one prompt for content-port completion.

Each prompt must be self-contained and usable in a fresh session.

### Deliverable 5: Orchestration map

Create a planning-level orchestration map showing:
- human coordinator role,
- briefing pack role,
- task prompt role,
- where agent outputs go,
- how decisions are locked,
- how conflicts are escalated.

## Required content handling

You must explicitly incorporate and preserve any planning-relevant v1.0 content related to:
- wizard/onboarding flows,
- guest mode,
- distribution strategy,
- cost visibility UX,
- trust and permissions UX,
- performance-tier UX,
- doctrine-sensitive user experience details.

Do not collapse these into vague summaries if they affect product shape.

## Output format

Work in planning documents, not casual notes.

For each created or updated artifact:
- use clear filenames,
- include status at top (`draft`, `working`, or `locked`),
- include last-updated date,
- include related dependencies,
- include open questions if any remain.

Also produce a short session-end index that lists:
- files created,
- files updated,
- files unchanged but relied on,
- unresolved issues,
- recommended next session.

## Quality bar

Do not optimize for speed by flattening strategic distinctions.  
Do not produce generic startup planning artifacts.  
Do not recommend commodity wrappers for moat-defining layers.  
Do not silently drift away from Tauri-first long-term desktop strategy.  
Do not weaken the assistant/companion quality target.

The planning output should reflect a premium, moat-aware, architecture-serious product family, not a generic SaaS app. This is consistent with current guidance that the human role in agentic software work is orchestration, standards-setting, and evaluation of outputs against strategic constraints. [cite:265][cite:268]

## If blocked

If blocked by missing context:
1. state exactly what is missing,
2. identify which deliverable is affected,
3. propose the narrowest assumption needed,
4. continue with everything else that can still be completed.

Do not stop early if partial completion is possible.

## Final response requirements

At the end of the session, return:
1. a concise executive summary,
2. a file inventory,
3. locked decisions carried forward,
4. open issues,
5. recommended next action.

Begin now by reading the planning folder and the latest handoff file, then produce the session-start summary before any new planning artifacts.
