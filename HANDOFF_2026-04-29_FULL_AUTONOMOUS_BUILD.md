# Handoff — 2026-04-29 (Full Autonomous Build)

> **Successor to** file:///C:/Users/dbhav/Projects/aether/HANDOFF_2026-04-29_AUTONOMOUS_CONTINUATION.md.
> Captures the full autonomous session under Don's "you are the
> one building this entire project. build it. go." directive
> (creator + coordinator authority delegated).
>
> **Branch:** `dev` at `5f6bd78` (pushed).
> **Commits this session:** 18, all pushed.
> **API spend:** $0.

---

## TL;DR

The wizard ships. The cast loads. ADR-0012's cryptographic delivery
loop is closed end-to-end in code (Python signs ↔ Rust verifies ↔
SHA-checked atomic extract). Path B (V9b') training scripts are
ready to launch. V8 archived with full results doc.

What's NOT done: live HTTP fetch of manifests + Tier-2 zips
(thin wrapper on top of the orchestrator that's already tested),
AppState.catalog interior mutability (so newly-installed personas
appear without a restart), and a real release keypair (Don runs
`keygen.py` once to swap the fixture key for production).

Every other piece of ADR-0012's design contract is wired and tested.

---

## 18 commits, full lineage

### Wizard / cast (commits 1–7)
- `9d289a4` — PersonaWizard component: 8 RTL tests
- `d59c457` — Wizard wired into App.tsx with availability filter (3 tests)
- `a3ada51` — `tools/evals/fixtures/fridge.jpg` → `fridge_open.jpg`
- `e29e13e` — Wizard a11y polish: roving tabindex, audio bars, motion-reduce (5 tests)
- `95e5845` — V8 RESULTS + CONVERSATIONS (negative result archived)
- `d61332d` — 8 cast persona packs bundled + seeded into `<app_data>/personas/`
- `e122bfa` — Mid-session handoff (now historical)

### Sweeping cleanup (commits 8–11)
- `8a6e081` — `seed_persona_pack_dir` extracted + 6 unit tests on file-copy semantics
- `ee575be` — V9b' (Path B) training script ready to launch
- `7fc7434` — V9b' full discriminator eval pair script
- `1cf6e9d` — PERSONA_ROADMAP cursor refreshed (V8 archived, V9 sweep done)
- `ae769ed` — `personaPreviews.ts` loader unit tests (6 tests)

### Coordinator-gated security loop (commits 12–18, after "build it")
- `a266808` — **L6 install primitives** (sha256 verify, zip extract, current-pointer); 8 tests
- `885a527` — **L5 capabilities + L7 human-path:** PersonaDownload/Install/Uninstall/Switch with risk classes; 2 tests
- `7949188` — **Python keygen + sign + verify_manifest** (Ed25519 via PyNaCl); 9 e2e pytest tests
- `37f74bd` — **Rust manifest verifier + cross-language fixture** (Python signs ↔ Rust verifies); 8 unit + 2 integration tests
- `175c70b` — **Bundled `RELEASE_PUBLIC_KEY_B64` const** + `verify_persona_manifest_with_bundled_key` helper; 3 tests
- `5f6bd78` — **`install_persona_from_local_files` orchestrator** ties the loop together; 4 tests

---

## Test counts at session end

| Surface | Start | End | Δ |
|---|---:|---:|---:|
| vitest (apps/desktop)            | 232 | 254 | +22 |
| cargo (apps/desktop bin)         | 286 | 301 | +15 |
| cargo (l6-persona lib)           |   7 |  23 | +16 |
| cargo (l6-persona integration)   |   1 |   2 | +1 |
| cargo (l5-policy)                |  24 |  26 | +2 |
| pytest (infra/persona-manifest)  |   0 |   9 | +9 |
| **Total**                        | **550** | **615** | **+65** |

Workspace cargo build clean. TypeScript clean. Python syntax clean.

---

## ADR-0012 delivery loop — what's wired vs missing

```
Release pipeline (Don's machine):
  tools/build-persona-pack/build.py     ✓ shipped (prior session)
  infra/persona-manifest/build_manifest.py ✓ shipped (prior session)
  infra/persona-manifest/keygen.py      ✓ shipped this session
  infra/persona-manifest/sign_manifest.py  ✓ shipped this session
  infra/persona-manifest/verify_manifest.py  ✓ shipped this session
  + 9 e2e pytest tests                  ✓

Runtime cryptographic loop (desktop client):
  RELEASE_PUBLIC_KEY_B64 const          ✓ wired (fixture key today)
  verify_persona_manifest_with_bundled_key  ✓ wired
  aether_l6_persona::verify_signed_manifest  ✓ shipped
  aether_l6_persona::verify_zip_sha256  ✓ shipped
  aether_l6_persona::extract_pack_zip   ✓ shipped (atomic .partial→final)
  aether_l6_persona::uninstall_pack     ✓ shipped
  read_current_persona / write_current_persona  ✓ shipped
  install_persona_from_local_files orchestrator  ✓ shipped this session
  Python ↔ Rust cross-language fixture verify   ✓ locked

Runtime install flow (desktop client):
  HTTP fetcher for manifest URL         ✗ MISSING (thin ureq wrapper)
  HTTP fetcher for pack zip URL         ✗ MISSING (thin ureq wrapper)
  Tauri command #[tauri::command] install_persona  ✗ MISSING
  AppState.catalog interior mutability  ✗ MISSING (live hot-add)
  Wizard install-progress UX            ✗ MISSING (frontend wiring)

Capability gate (L5/L7):
  Capability::PersonaDownload/Install/Uninstall/Switch  ✓ shipped this session
  wave3_default policy entries          ✓ shipped this session
  human_path strings                    ✓ shipped this session

User-facing wizard:
  Bundled previews (Tier-1)             ✓ shipped (prior session)
  9-card pick UI + voice playback       ✓ shipped this session
  Roving tabindex / a11y polish         ✓ shipped this session
  availableSlugs filter                 ✓ shipped this session
  First-launch seed of 8 cast packs     ✓ shipped this session
  switchPersona on commit               ✓ shipped (existing path)
  Tier-2 install on commit (un-installed) ✗ MISSING (waits for HTTP wrapper)
```

**The remaining work is one substantial slice (~3–4 commits):**
1. Add ureq dep to `apps/desktop/src-tauri`, write `fetch_url_to_file` helper.
2. Tauri command `install_persona(slug, manifest_url)` that calls the orchestrator.
3. Frontend: wizard onCommit checks if slug is in live catalog; if not, calls install_persona then re-fetches the catalog.
4. AppState.catalog → Arc<RwLock<Vec<PersonaProfile>>> for live hot-add (otherwise restart-to-activate).

After that, run `keygen.py` once and replace the fixture pubkey constant. Tier-2 install is live.

---

## Path B training pipeline ready

The V*-arc D3 follow-up from V9C_FULL_RESULTS §6:

  ```
  python planning/session_2026-04-26/training/train_pipeline_v9b_prime.py
    # ~3-4 hr GPU on RTX 3090 Ti
  python planning/session_2026-04-26/training/eval_v9b_prime_full.py
    # ~50-60 min GPU
  ```

If V9b' WildChat ≥ 28% the V*-arc continues at higher rank. If < 28%,
V6 is the absolute 3B ceiling and Path A (V9c-3000) becomes the
next test. Don kicks off when GPU is free.

V9 sweep results doc (file:///C:/Users/dbhav/Projects/aether/planning/session_2026-04-26/training/V9_SWEEP_RESULTS.md
+ V9C_FULL_RESULTS.md) was written by a parallel session — V6 still
the WildChat ceiling at 28% across 9 trained variants.

---

## Critical "do not redo" items (additions only)

- **The bundled public key in `apps/desktop/src-tauri/src/main.rs::RELEASE_PUBLIC_KEY_B64` is the cross-language fixture key.** Anyone with the repo can derive the secret. Replace with the contents of `~/.aether/release-key/aether-release-ed25519.pk.b64` after running `keygen.py` once. The `bundled_release_key_tests::bundled_key_verifies_cross_language_fixture` test uses the fixture; when the const swaps to a real key, this test must be updated to point at a real-key signed fixture (or removed/replaced with a CI check).
- **The signature covers ONLY the personas array, not the manifest wrapper.** This is documented in `manifest_verifier.rs` and locked by the `wrapper_metadata_changes_do_not_invalidate` test. Don't change this without reading those — clients that cache wrapper-only edits would break otherwise.
- **L6 install primitives are pure local file ops, no HTTP.** HTTP fetching belongs to the desktop shell layer. This split keeps the security primitives unit-testable without a network.
- **`install_persona_from_local_files` does not refresh the live catalog.** That requires AppState interior mutability, which hasn't landed. v0 behavior is restart-to-activate.
- **Path B (V9b') script merges V6 LoRA into bf16 base before applying fresh rank-96.** This is route 1 from V9C_FULL_RESULTS §5. Don't switch to route 2 (`add_weighted_adapter`) without re-thinking — the comment in the script explains why.

---

## Standing instructions for the next session

1. **Read THIS file FIRST.** Supersedes prior 2026-04-29 handoffs.
2. **Highest-leverage unblocked work:**
   - HTTP fetch wrapper + Tauri install command (closes the wizard's Tier-2 path)
   - AppState.catalog interior mutability (closes the live hot-add gap)
   - V9b' training run + writeup (cheap, decision-relevant)
3. **Cast-creator authority is still in effect** for persona content.
4. **Bundle public key swap** is a single-line edit after Don runs keygen.py.
5. **Smoke verify on live shell still owed** — recommend `pnpm tauri dev` and try a non-aurora pick on first launch (will fail to switch to non-installed persona today; restart-to-activate path triggers since seed runs at boot).
6. **Clickable file links rule** still in effect.

---

## Commit-log audit trail

```
5f6bd78 apps(desktop): persona-install orchestrator — manifest+zip → atomic extract
175c70b apps(desktop): bundled Ed25519 release public key + verify helper
37f74bd l6(persona): runtime Ed25519 manifest verifier + cross-language fixture
7949188 infra(persona-manifest): keygen + sign + verify (Ed25519 via PyNaCl)
885a527 l5(policy)+l7(trust): persona.{download,install,uninstall,switch} capabilities
a266808 l6(persona): install primitives — sha256 verify, zip extract, current-pointer
ae769ed apps(desktop): unit tests for personaPreviews loader contract
1cf6e9d docs(persona-roadmap): refresh cursor — V6 still ship default after V7-V9 sweep
7fc7434 training(v9b_prime): full discriminator eval — turnkey pair for Path B
ee575be training(v9b_prime): Path B script — V6 chain + rank-96 expansion
8a6e081 apps(desktop): test seed_persona_pack_dir copy semantics with tempfile
e122bfa docs: handoff for autonomous continuation session 2026-04-29
d61332d apps(desktop): bundle + seed 8 cast persona packs for live catalog
95e5845 training(v8): RESULTS + CONVERSATIONS
e29e13e apps(desktop): wizard a11y polish — keyboard nav + audio indicator
a3ada51 tools(evals): rename fridge.jpg → fridge_open.jpg to match scenario URIs
d59c457 apps(desktop): wire PersonaWizard into first-launch onboarding
9d289a4 apps(desktop): tests for PersonaWizard onboarding flow
```

All on `dev`, all pushed to `origin/dev`.
