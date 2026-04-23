# Memory V2 step 6 execution report — 2026-04-23

**Run 3 of six-run roadmap (2026-04-23).** Embeddings, opt-in,
local-only. Two reserved decisions from MEMORY-V2-ARCHITECTURE.md
§9 closed via ADR-0002.

## What shipped

| SHA | Subject |
| --- | --- |
| `e135c2a` | feat(memory): Memory V2 step 6 — embeddings (opt-in, local-only) |

Single commit. Scope was cohesive enough (L5 capability → L2
trait + impl → shell wiring + tests) that splitting would have
added friction without aiding review.

### ADR-0002 accepted

Reserved decisions resolved (see
`docs/adr/ADR-0002-embeddings-provider-and-vector-backend.md`):

1. **Provider**: Ollama `/api/embeddings` with model
   `nomic-embed-text` as default. Reuses the existing Ollama
   daemon; 768-dim; open weights; CPU-fast.
2. **Vector backend**: in-process flat-file
   (`HashMap<MemoryId, Vec<f32>>`) with optional JSONL
   persistence per domain. Zero new heavy deps. Linear cosine
   scan; swappable via trait when measured slowness warrants.
3. **L5 capability**: `MemoryEmbed` (Auto, Low risk).
4. **Feature gate**: `embeddings` on `aether-l2-memory`.
5. **Embed-eligible domains**: Durable / Projects / Artifacts.
6. **Out of scope**: retrieval wiring in the turn engine, vector
   index backends, embed-on-retention-sweep, UI beyond the
   existing Settings toggle.

### L5 (`packages/l5-policy`)

- `Capability::MemoryEmbed` variant.
- `wave3_default` preset: `Auto`, `RiskClass::Low`.
- `default_risk_for` match arm.
- Round-trip serde test.
- Preset registration test.

### L7 (`packages/l7-trust`)

- `human_capability` string label: `"memory.embed"`.

### L2 (`packages/l2-memory`)

- New `src/embeddings.rs` module, feature-gated.
- `EmbeddingProvider` + `EmbeddingStore` traits.
- `FlatFileEmbeddingStore`: domain-partitioned, cosine `query_nearest`,
  atomic JSONL persistence via write-to-temp + rename.
- `OllamaEmbeddingProvider`: blocking `ureq` POST. Env vars
  `AETHER_EMBED_OLLAMA_BASE_URL`, `AETHER_EMBED_OLLAMA_MODEL`
  (ADR-0002 §Decisions 1).
- `StubEmbedder`: test seam; normalises via hash distribution so
  similar text → similar vector.
- `EMBED_ELIGIBLE_DOMAINS` public const.
- Cargo feature `embeddings` with optional `serde_json` + `ureq`
  (pure-Rust HTTP client, same pattern L4 uses).
- 12 unit tests: eligibility, upsert/replace, delete-returns-bool,
  top-k cosine, k=0 + empty-store edge cases, zero-vector error,
  persistence round-trip, stub determinism, stub similarity
  ordering, Ollama provider label.

### Shell (`apps/desktop/src-tauri`)

- `AppState` grows `embedding_store: Arc<dyn EmbeddingStore>` and
  `embedding_provider: RwLock<Arc<dyn EmbeddingProvider>>`. Tests
  can swap in `StubEmbedder`; Settings can hot-swap the provider.
- `memory_service.rs`:
  - `telemetry_kind::EMBEDDED = "memory_embedded"`.
  - `maybe_embed_on_write`: runs on MemoryWrite Allow only when
    `memory_config.embeddings.enabled` AND domain is
    embed-eligible. L5-audited via `MemoryEmbed`; provider /
    store failures trace-warn, never block primary write.
  - `delete_embedding`: paired forget on per-item MemoryForget
    Allow. Silent no-op when no embedding exists.
- `perform_memory_write` passes a content snapshot to
  `maybe_embed_on_write` before the record moves into
  `memory.append`.
- `Cargo.toml`: `aether-l2-memory` now enables `embeddings`
  feature alongside `sqlite-backend`.
- 6 new tests: disabled-path zero-ops, enabled-Durable writes +
  telemetry, Session-domain skip, all three eligible domains
  embed, per-item forget removes paired embedding, provider
  failure doesn't block primary write.

## Check matrix (all green)

| Check | Result |
| --- | --- |
| `cargo fmt --all -- --check` | clean |
| `cargo check --workspace` | clean |
| `cargo test --workspace` | all pass |
| `cargo test -p aether-l2-memory --features "sqlite-backend embeddings"` | 33 session + 1 smoke + 16 sqlite |
| `cargo test -p aether-l5-policy` | 20 engine + 11 + 7 (no new failures) |
| `cargo test -p aether-l4-router --features …` | 96 / 96 |
| `apps/desktop/src-tauri cargo test --all-features` | **210 / 210** (was 204, +6 embed) |
| `python tools/lint-layer-boundaries/check.py` | 0 violations |
| `python tools/lint-vision-doc` / `voice-doc` / `presence-doc` / `quality-doc` | OK |
| `apps/desktop && pnpm typecheck` | clean |
| `apps/desktop && pnpm build` | 237 / 68 kB |
| `apps/desktop && pnpm test` | 185 / 185 |

## Done-when checklist

- [x] `cargo test --workspace` passes including new embedding tests.
- [x] With `embeddings.enabled = false` (default), behaviour is
      byte-identical to today.
- [x] With `embeddings.enabled = true` + known provider id, each
      `memory_write` Allowed outcome produces an embedding row.
- [x] L5 audit is coherent — one audit row per embedding write
      via `MemoryEmbed`.
- [x] `MEMORY-V2-ARCHITECTURE.md` §10 item 6 reflects reality.

## In-flight decisions (captured in ADR-0002)

- Best-effort embeds (provider failure → WARN + no-op, primary
  write unaffected). Rationale: embeddings are additive signal,
  not required state; the user's memory row is still complete
  without an embedding row.
- Domain-partitioned flat-file JSONL persistence. Rewrite on
  every mutation (not append-only): keeps tests and inspection
  trivial, and personal-scale row counts stay sub-ms to serialise.
- Shell's `aether-l2-memory` dependency pinned to
  `features = ["sqlite-backend", "embeddings"]`. `embeddings`
  feature is always on in the shipped binary; opt-in is a
  runtime toggle, not a compile-time one.
- `MemoryEmbed` is Low-risk Auto. The per-domain user decision
  lives on `MemoryWrite`; embedding the same content is a
  downstream side effect, not a second user-gated action.

## Out of scope (intentional)

- Retrieval wiring in the turn engine — deferred to a future
  slice; `query_nearest` is available on the store, the turn
  engine does not consume it yet.
- Vector index backends (sqlite-vec, lancedb, HNSW) — ADR-0002
  §Alternatives covers rejection rationale; revisit when
  measured.
- Embed-on-retention-sweep — waits for the domain-typed durable
  store (Risk C from 2026-04-23 Run 1+2 handoff).
- UI beyond the existing Settings toggle — the toggle already
  ships from step 2; step 6 is the runtime consumer.
