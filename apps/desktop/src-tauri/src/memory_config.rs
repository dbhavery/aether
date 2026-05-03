//! Memory V2 step 2 — `memory.json` policy/config surface.
//!
//! Owns `<app_data>/memory.json` — the user-owned memory-system
//! policy per `docs/MEMORY-V2-ARCHITECTURE.md` §3. Contains no memory
//! items themselves (those live in the SQLite durable store); only
//! the per-domain policies that govern writes, retention, and the
//! embeddings opt-in.
//!
//! ## Contract (same shape every other Companion config uses)
//!
//! - **Additive.** New domains or fields may be added in future
//!   builds.
//! - **Default-safe on read.** Every field has `#[serde(default)]`
//!   producing a design-doc-safe value.
//! - **Unknown fields silently ignored on read**; no
//!   `#[serde(deny_unknown_fields)]`.
//! - **Unknown fields dropped on rewrite** — documented limitation,
//!   same as `presence_config.rs` / `mic_permissions.rs`.
//! - **Malformed JSON → default + WARN.**
//! - **Atomic writes** — write-to-temp + rename.
//! - **No L2 consumer in this slice.** Step 2 only lands the
//!   policy/config surface. Steps 3–7 (plumbing, Memory tab, sweep,
//!   embeddings, rot guard) consume this.
//!
//! ## Scope
//!
//! Matches design §3 exactly — six domains, three risk levels, one
//! embeddings toggle. No per-item overrides, no sampled-read
//! controls, no cross-device sync. All deliberate per the doc's
//! "deferred to later tracks" list.

use std::collections::BTreeMap;
use std::fs;
use std::io::{self, ErrorKind};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

// ADR-0001 (2026-04-23): `MemoryDomain` is hosted in `aether-l2-memory`
// so background jobs (retention sweep, embeddings worker) can speak
// the taxonomy without coupling to the desktop binary. Re-exported
// here so existing `memory_config::MemoryDomain` callsites continue to
// compile unchanged.
pub use aether_l2_memory::MemoryDomain;

/// Policy risk posture per domain. Mirrors the tri-state the media
/// and mic permissions already use, so the Settings UI can share
/// vocabulary across surfaces.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MemoryRisk {
    /// Write proceeds without an approval modal. L5 still records an
    /// audit row — Auto means "no interruption", not "no audit".
    Auto,
    /// Write surfaces the approval modal; user-sensitive domains
    /// default here per design §4.
    Ask,
    /// Write is rejected outright. Rarely useful but the state
    /// machine would be incomplete without it.
    Deny,
}

/// Retention rule for a single domain. `None` = keep until the user
/// explicitly forgets. A positive integer = rolling TTL in days,
/// enforced by the retention sweep (a later slice).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum RetentionDays {
    /// Keep until forgotten.
    Forever(Option<u16>),
    /// Numeric TTL in days.
    Days(u16),
}

impl RetentionDays {
    /// Resolve to an optional day count. `Forever(None)` and
    /// `Days(0)` both mean "keep forever" for the UI.
    pub fn as_days(self) -> Option<u16> {
        match self {
            RetentionDays::Forever(v) => v.and_then(|d| if d == 0 { None } else { Some(d) }),
            RetentionDays::Days(d) => (d > 0).then_some(d),
        }
    }
}

/// Top-level memory policy snapshot. Cheap to clone; callers treat
/// it as a value. Serde layout matches `docs/MEMORY-V2-ARCHITECTURE.md`
/// §3.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MemoryConfig {
    /// Per-domain retention in days. `null` = keep forever. Missing
    /// domains fall back to design defaults (see
    /// `MemoryConfig::defaults`).
    #[serde(default = "default_retention_map")]
    pub retention_days: BTreeMap<MemoryDomain, Option<u16>>,
    /// Per-domain default risk posture for writes. Missing domains
    /// fall back to design defaults.
    #[serde(default = "default_risk_map")]
    pub default_risk: BTreeMap<MemoryDomain, MemoryRisk>,
    /// Embeddings subsystem config. Design §3: default disabled.
    #[serde(default)]
    pub embeddings: EmbeddingsConfig,
    /// Retrieval wiring config — top-K cap and future retrieval knobs.
    /// Additive per ADR-0005; unknown nested fields fall back to the
    /// `RetrievalConfig` default the same way `embeddings` does.
    #[serde(default)]
    pub retrieval: RetrievalConfig,
}

/// Embeddings opt-in block. `enabled = false` is the ship default;
/// enabling requires a provider to be named (a later slice wires a
/// real Ollama or llama.cpp embedding adapter).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EmbeddingsConfig {
    /// Master switch. Default `false` — no automatic embedding.
    #[serde(default)]
    pub enabled: bool,
    /// Named embedding provider id. `None` when disabled or no
    /// provider has been chosen yet.
    #[serde(default)]
    pub provider: Option<String>,
}

impl Default for EmbeddingsConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            provider: None,
        }
    }
}

/// Retrieval wiring config (ADR-0005 §Decision 3). Owns the top-K cap
/// applied after rank. Future fields (min-score floor, per-domain
/// multipliers) land additively under the same key.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct RetrievalConfig {
    /// Maximum number of ranked hits returned per turn. ADR-0005
    /// §Decision 3 ships the default at 5; zero disables retrieval
    /// injection without flipping `embeddings.enabled`.
    #[serde(default = "default_retrieval_max_items")]
    pub max_items: u32,
}

fn default_retrieval_max_items() -> u32 {
    5
}

impl Default for RetrievalConfig {
    fn default() -> Self {
        Self {
            max_items: default_retrieval_max_items(),
        }
    }
}

fn default_retention_map() -> BTreeMap<MemoryDomain, Option<u16>> {
    // Per design §1 defaults table: Durable = 30 days, everything
    // else = keep until forgotten.
    let mut m = BTreeMap::new();
    m.insert(MemoryDomain::Session, None);
    m.insert(MemoryDomain::Durable, Some(30));
    m.insert(MemoryDomain::Facts, None);
    m.insert(MemoryDomain::Projects, None);
    m.insert(MemoryDomain::Preferences, None);
    m.insert(MemoryDomain::Artifacts, None);
    m
}

fn default_risk_map() -> BTreeMap<MemoryDomain, MemoryRisk> {
    // Per design §4: user-sensitive (Facts, Artifacts) default Ask;
    // standard domains default Auto.
    let mut m = BTreeMap::new();
    m.insert(MemoryDomain::Session, MemoryRisk::Auto);
    m.insert(MemoryDomain::Durable, MemoryRisk::Auto);
    m.insert(MemoryDomain::Facts, MemoryRisk::Ask);
    m.insert(MemoryDomain::Projects, MemoryRisk::Auto);
    m.insert(MemoryDomain::Preferences, MemoryRisk::Auto);
    m.insert(MemoryDomain::Artifacts, MemoryRisk::Ask);
    m
}

impl MemoryConfig {
    /// Canonical defaults per design §3.
    pub fn defaults() -> Self {
        Self {
            retention_days: default_retention_map(),
            default_risk: default_risk_map(),
            embeddings: EmbeddingsConfig::default(),
            retrieval: RetrievalConfig::default(),
        }
    }

    /// Resolve the risk posture for a given domain, falling back to
    /// the design default if the domain has been dropped from the
    /// persisted map (additive-safe).
    pub fn risk_for(&self, domain: MemoryDomain) -> MemoryRisk {
        self.default_risk
            .get(&domain)
            .copied()
            .unwrap_or_else(|| default_risk_map()[&domain])
    }

    /// Resolve retention in days for a given domain. `None` = keep
    /// until forgotten. Missing entries fall back to design defaults.
    pub fn retention_for(&self, domain: MemoryDomain) -> Option<u16> {
        match self.retention_days.get(&domain) {
            Some(v) => *v,
            None => default_retention_map()[&domain],
        }
    }
}

impl Default for MemoryConfig {
    fn default() -> Self {
        Self::defaults()
    }
}

/// Load the persisted memory config from `path`, falling back to
/// defaults if the file is missing or malformed. Intentionally
/// lenient — a corrupt file must not take down the shell.
pub fn load_or_default(path: &Path) -> MemoryConfig {
    match fs::read_to_string(path) {
        Ok(s) => match serde_json::from_str::<MemoryConfig>(&s) {
            Ok(cfg) => cfg,
            Err(e) => {
                tracing::warn!(
                    "memory config file {} is malformed ({e}); using defaults",
                    path.display()
                );
                MemoryConfig::defaults()
            }
        },
        Err(e) if e.kind() == ErrorKind::NotFound => MemoryConfig::defaults(),
        Err(e) => {
            tracing::warn!(
                "could not read memory config file {}: {e}; using defaults",
                path.display()
            );
            MemoryConfig::defaults()
        }
    }
}

/// Atomically persist `cfg` to `path`, creating parent directories
/// as needed. Write-to-temp + rename so a crash in the middle of a
/// write cannot leave a half-written file the next boot will reject.
pub fn save(path: &Path, cfg: &MemoryConfig) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let body =
        serde_json::to_string_pretty(cfg).map_err(|e| io::Error::new(ErrorKind::InvalidData, e))?;
    fs::write(&tmp, body)?;
    fs::rename(&tmp, path)?;
    Ok(())
}

/// Resolve the canonical memory-config path beside the other shell-
/// state files. Tests pass any directory.
pub fn config_path_for(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("memory.json")
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn defaults_match_design_doc() {
        let c = MemoryConfig::defaults();
        // §1 defaults table.
        assert_eq!(c.retention_for(MemoryDomain::Durable), Some(30));
        assert_eq!(c.retention_for(MemoryDomain::Session), None);
        assert_eq!(c.retention_for(MemoryDomain::Facts), None);
        // §4 defaults table.
        assert_eq!(c.risk_for(MemoryDomain::Facts), MemoryRisk::Ask);
        assert_eq!(c.risk_for(MemoryDomain::Artifacts), MemoryRisk::Ask);
        assert_eq!(c.risk_for(MemoryDomain::Durable), MemoryRisk::Auto);
        assert_eq!(c.risk_for(MemoryDomain::Session), MemoryRisk::Auto);
        // Embeddings ship off per §3.
        assert!(!c.embeddings.enabled);
        assert!(c.embeddings.provider.is_none());
        // ADR-0005 §Decision 3: retrieval top-K defaults to 5.
        assert_eq!(c.retrieval.max_items, 5);
    }

    #[test]
    fn retrieval_config_roundtrips_and_falls_back_when_absent() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("memory.json");
        // Missing `retrieval` block — must default to 5, not 0.
        fs::write(&path, r#"{ "embeddings": { "enabled": false } }"#).unwrap();
        let loaded = load_or_default(&path);
        assert_eq!(loaded.retrieval.max_items, 5);

        // Explicit override roundtrips.
        let mut cfg = MemoryConfig::defaults();
        cfg.retrieval.max_items = 12;
        save(&path, &cfg).expect("save");
        let reloaded = load_or_default(&path);
        assert_eq!(reloaded.retrieval.max_items, 12);
    }

    #[test]
    fn all_domains_enumerated() {
        assert_eq!(MemoryDomain::ALL.len(), 6);
    }

    #[test]
    fn domain_labels_are_stable() {
        assert_eq!(MemoryDomain::Session.label(), "session");
        assert_eq!(MemoryDomain::Durable.label(), "durable");
        assert_eq!(MemoryDomain::Facts.label(), "facts");
        assert_eq!(MemoryDomain::Projects.label(), "projects");
        assert_eq!(MemoryDomain::Preferences.label(), "preferences");
        assert_eq!(MemoryDomain::Artifacts.label(), "artifacts");
    }

    #[test]
    fn load_or_default_when_missing_returns_defaults() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("missing.json");
        assert_eq!(load_or_default(&path), MemoryConfig::defaults());
    }

    #[test]
    fn save_then_load_roundtrips() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nested").join("memory.json");
        let mut original = MemoryConfig::defaults();
        original
            .default_risk
            .insert(MemoryDomain::Facts, MemoryRisk::Deny);
        original
            .retention_days
            .insert(MemoryDomain::Durable, Some(7));
        original.embeddings.enabled = true;
        original.embeddings.provider = Some("ollama:bge-small".into());
        save(&path, &original).expect("save");
        let loaded = load_or_default(&path);
        assert_eq!(loaded, original);
    }

    #[test]
    fn load_or_default_falls_back_on_malformed_json() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("memory.json");
        fs::write(&path, "not json at all").unwrap();
        assert_eq!(load_or_default(&path), MemoryConfig::defaults());
    }

    #[test]
    fn unknown_fields_are_silently_ignored_on_read() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("memory.json");
        fs::write(
            &path,
            r#"{
                "retention_days": { "session": null, "durable": 60 },
                "default_risk": { "facts": "ask" },
                "embeddings": { "enabled": false },
                "future_knob": "some-value"
            }"#,
        )
        .unwrap();
        let c = load_or_default(&path);
        assert_eq!(c.retention_for(MemoryDomain::Durable), Some(60));
    }

    #[test]
    fn unknown_fields_are_dropped_on_rewrite() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("memory.json");
        fs::write(&path, r#"{ "future_knob": ["x"] }"#).unwrap();
        let loaded = load_or_default(&path);
        save(&path, &loaded).expect("rewrite");
        let rewritten = fs::read_to_string(&path).unwrap();
        assert!(rewritten.contains("\"retention_days\""));
        assert!(!rewritten.contains("future_knob"));
    }

    #[test]
    fn partial_config_preserves_provided_fields_and_defaults_the_rest() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("memory.json");
        // Only override one field; everything else falls back via the
        // `risk_for` / `retention_for` lookup path.
        fs::write(&path, r#"{ "default_risk": { "durable": "ask" } }"#).unwrap();
        let c = load_or_default(&path);
        assert_eq!(c.risk_for(MemoryDomain::Durable), MemoryRisk::Ask);
        // Facts still defaults to Ask (user-sensitive).
        assert_eq!(c.risk_for(MemoryDomain::Facts), MemoryRisk::Ask);
        // Durable retention default still applies.
        assert_eq!(c.retention_for(MemoryDomain::Durable), Some(30));
    }

    #[test]
    fn missing_map_entries_fall_back_on_lookup() {
        // A persisted file that drops a domain entirely (e.g. a
        // future build removed one, or a hand-edit) must not crash
        // the shell.
        let mut cfg = MemoryConfig::defaults();
        cfg.default_risk.remove(&MemoryDomain::Projects);
        assert_eq!(cfg.risk_for(MemoryDomain::Projects), MemoryRisk::Auto);
    }

    #[test]
    fn config_path_for_lives_beside_app_data() {
        let dir = Path::new("/tmp/aether-test");
        let p = config_path_for(dir);
        assert_eq!(p, Path::new("/tmp/aether-test/memory.json"));
    }
}
