//! ADR-0006 hardware tier model — `tier.json` + tier resolution.
//!
//! Persists the user-selected tier alongside the auto-detected
//! recommendation and the hardware snapshot that produced it. Same
//! contract as `memory_config.rs` and `presence_config.rs`:
//!
//! - Additive serde — new fields land with `#[serde(default)]`.
//! - Default-safe on read.
//! - Unknown fields silently ignored on read; dropped on rewrite.
//! - Malformed JSON → defaults + WARN.
//! - Atomic write (write-to-temp + rename).
//!
//! Tier resolution (`recommend_tier`) implements ADR-0006 §Decision 3:
//! always recommend the *highest* tier whose minimum hardware envelope
//! the detected machine meets or exceeds. The 50% headroom rule
//! (ADR-0006 §Constraint 2) is applied here at *recommendation* time;
//! it is not a runtime cap, per the quality-first amendment.

use std::fs;
use std::io::{self, ErrorKind};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::hardware::{GpuKind, HardwareSnapshot};

/// The three tier identities defined by ADR-0006 §Decision 1.
/// Provisional names (Spark / Flame / Forge) chosen to match Companion's
/// warmth / fire palette and avoid implying a moral hierarchy.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Tier {
    /// CPU-only / integrated-GPU envelope. Avatar medium is real
    /// recorded video — no real-time neural rendering.
    Spark,
    /// Mid-range discrete GPU. Per-tier VRAM budget after the 50%
    /// recommended-floor rule: ~6–8 GB. All standard features on.
    Flame,
    /// High-end discrete GPU. Effective VRAM budget ~12+ GB. Every
    /// capability on, largest viable models, full-fidelity avatar.
    Forge,
}

impl Tier {
    /// Stable wire string used for logs / telemetry / TS bindings.
    pub fn label(self) -> &'static str {
        match self {
            Tier::Spark => "spark",
            Tier::Flame => "flame",
            Tier::Forge => "forge",
        }
    }

    /// Iteration order for UI surfaces that render all three tier
    /// cards.
    pub const ALL: &'static [Tier] = &[Tier::Spark, Tier::Flame, Tier::Forge];
}

/// Persisted shape of `<app_data>/tier.json`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TierConfig {
    /// The tier currently in effect — what every consumer reads.
    /// Defaults to `Spark` until detection runs (conservative
    /// floor; means "no detection yet" without crashing the shell
    /// on first launch).
    #[serde(default = "default_tier")]
    pub selected_tier: Tier,

    /// The tier `recommend_tier` returned at last detection. May
    /// differ from `selected_tier` when the user has overridden.
    /// Settings UI shows the divergence as "your hardware suggests
    /// X" hint.
    #[serde(default = "default_tier")]
    pub detected_tier: Tier,

    /// Wall-clock millis of last successful detection. `0` if
    /// detection has never run.
    #[serde(default)]
    pub detected_at_ms: u64,

    /// Whether the user has explicitly chosen a tier different from
    /// the detected one. Set when `set_tier` is called with a tier
    /// that doesn't match `detected_tier`. Cleared when re-detection
    /// produces a tier matching the current selection.
    #[serde(default)]
    pub manual_override: bool,

    /// Snapshot of the hardware at last detection. Surfaced in the
    /// Settings UI so the user can see what was detected without
    /// re-running probes.
    #[serde(default = "HardwareSnapshot::unknown")]
    pub hardware_snapshot: HardwareSnapshot,
}

fn default_tier() -> Tier {
    Tier::Spark
}

impl TierConfig {
    /// Pre-detection defaults. Conservative — Spark tier, empty
    /// snapshot, no override flag.
    pub fn defaults() -> Self {
        Self {
            selected_tier: default_tier(),
            detected_tier: default_tier(),
            detected_at_ms: 0,
            manual_override: false,
            hardware_snapshot: HardwareSnapshot::unknown(),
        }
    }
}

impl Default for TierConfig {
    fn default() -> Self {
        Self::defaults()
    }
}

/// Implements ADR-0008 — recommend the highest tier from `device_type`
/// + `total_ram_gb`. **Replaces ADR-0006 §Decision 3** (which used
/// `wgpu::Limits::max_buffer_size` as a VRAM proxy and was proven
/// unreliable cross-backend during 2026-04-24 on-hardware validation
/// — see ADR-0008 §Context for the data).
///
/// The 50% headroom rule (ADR-0006 §Constraint 2) is applied here at
/// recommendation time on RAM. Quality-first amendment: this is the
/// *recommended floor*, not a runtime cap; users who dedicate their
/// hardware may safely allocate above 50% via manual override.
///
/// Rule:
/// - No GPU detected → Spark.
/// - Non-discrete adapter (Integrated / Cpu / Other) → Spark.
/// - Discrete adapter + total RAM >= 32 GB → Forge (workstation).
/// - Discrete adapter + total RAM >= 16 GB → Flame (enthusiast).
/// - Discrete adapter + total RAM < 16 GB → Spark (constrained).
///
/// Note: `gpu.vram_gb_estimate` is intentionally NOT consumed here.
/// It remains a populated diagnostic field on the snapshot but is
/// no longer a decision input — see ADR-0008 §Decision 3.
pub fn recommend_tier(snapshot: &HardwareSnapshot) -> Tier {
    let Some(gpu) = snapshot.gpu.as_ref() else {
        return Tier::Spark;
    };

    let is_discrete = matches!(gpu.kind, GpuKind::DiscreteGpu | GpuKind::VirtualGpu);
    if !is_discrete {
        return Tier::Spark;
    }

    // 50% headroom rule applied to RAM only. Effective_ram = total / 2.
    // Forge floor = 16 GB effective (32 GB total). Flame floor = 8 GB
    // effective (16 GB total).
    let effective_ram = snapshot.total_ram_gb / 2;
    if effective_ram >= 16 {
        Tier::Forge
    } else if effective_ram >= 8 {
        Tier::Flame
    } else {
        Tier::Spark
    }
}

/// Resolve the canonical `tier.json` path beside the other shell-state
/// files. Tests pass any directory.
pub fn config_path_for(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("tier.json")
}

/// Load the persisted tier config from `path`, falling back to
/// defaults if the file is missing or malformed. Lenient — corrupt
/// file must not block boot.
pub fn load_or_default(path: &Path) -> TierConfig {
    match fs::read_to_string(path) {
        Ok(s) => match serde_json::from_str::<TierConfig>(&s) {
            Ok(cfg) => cfg,
            Err(e) => {
                tracing::warn!(
                    "tier config file {} is malformed ({e}); using defaults",
                    path.display()
                );
                TierConfig::defaults()
            }
        },
        Err(e) if e.kind() == ErrorKind::NotFound => TierConfig::defaults(),
        Err(e) => {
            tracing::warn!(
                "could not read tier config file {}: {e}; using defaults",
                path.display()
            );
            TierConfig::defaults()
        }
    }
}

/// Atomically persist `cfg` to `path`, creating parent directories as
/// needed. Write-to-temp + rename so a crash mid-write cannot leave a
/// half-written file the next boot will reject.
pub fn save(path: &Path, cfg: &TierConfig) -> io::Result<()> {
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hardware::{GpuInfo, GpuKind};
    use tempfile::TempDir;

    fn gpu(kind: GpuKind, vram_gb: u32) -> GpuInfo {
        GpuInfo {
            vendor_id: "0x10de".into(),
            device_name: "Test GPU".into(),
            kind,
            backend: "Vulkan".into(),
            vram_gb_estimate: vram_gb,
        }
    }

    fn snap(g: Option<GpuInfo>, ram: u32) -> HardwareSnapshot {
        HardwareSnapshot {
            gpu: g,
            total_ram_gb: ram,
            cpu_cores: 8,
            disk_available_gb: Some(100),
            ollama_gpu_loaded: None,
            detected_at_ms: 1,
        }
    }

    #[test]
    fn no_gpu_falls_to_spark() {
        assert_eq!(recommend_tier(&snap(None, 64)), Tier::Spark);
    }

    #[test]
    fn integrated_gpu_falls_to_spark_regardless_of_ram() {
        let s = snap(Some(gpu(GpuKind::IntegratedGpu, 32)), 64);
        assert_eq!(recommend_tier(&s), Tier::Spark);
    }

    #[test]
    fn cpu_adapter_falls_to_spark() {
        let s = snap(Some(gpu(GpuKind::Cpu, 0)), 32);
        assert_eq!(recommend_tier(&s), Tier::Spark);
    }

    #[test]
    fn discrete_with_high_ram_recommends_forge() {
        // ADR-0008: discrete + 32 GB RAM (16 GB effective) hits Forge
        // floor. VRAM estimate intentionally ignored.
        let s = snap(Some(gpu(GpuKind::DiscreteGpu, 24)), 32);
        assert_eq!(recommend_tier(&s), Tier::Forge);
    }

    #[test]
    fn discrete_with_mid_ram_recommends_flame() {
        // ADR-0008: discrete + 16 GB RAM (8 GB effective) hits Flame
        // floor; doesn't reach Forge.
        let s = snap(Some(gpu(GpuKind::DiscreteGpu, 12)), 16);
        assert_eq!(recommend_tier(&s), Tier::Flame);
    }

    #[test]
    fn discrete_with_too_little_ram_falls_back_to_spark() {
        // ADR-0008: discrete with <16 GB total RAM (8 GB effective)
        // doesn't meet Flame floor. Modern LLM serving needs system
        // memory for prompt tokenisation + KV before VRAM offload.
        let s = snap(Some(gpu(GpuKind::DiscreteGpu, 24)), 4);
        assert_eq!(recommend_tier(&s), Tier::Spark);
    }

    #[test]
    fn discrete_with_low_vram_estimate_no_longer_demotes() {
        // ADR-0008 invariant: vram_gb_estimate is NOT a decision input.
        // A 4 GB discrete card with 32 GB RAM is now Forge; under the
        // old ADR-0006 §3 rule it would have been Spark.
        let s = snap(Some(gpu(GpuKind::DiscreteGpu, 4)), 32);
        assert_eq!(recommend_tier(&s), Tier::Forge);
    }

    #[test]
    fn discrete_with_unreliable_vram_sentinel_picks_correct_tier() {
        // ADR-0008 motivating case: Vulkan often returns u64::MAX as
        // max_buffer_size, which previously divided by 1 GB to ~4
        // billion and trivially passed the Forge floor. The new rule
        // is independent of that field — verify the tier comes from
        // RAM, not from the bogus VRAM number.
        let s = snap(Some(gpu(GpuKind::DiscreteGpu, u32::MAX)), 16);
        // 16 GB RAM = Flame, regardless of the sentinel VRAM.
        assert_eq!(recommend_tier(&s), Tier::Flame);

        let s2 = snap(Some(gpu(GpuKind::DiscreteGpu, u32::MAX)), 32);
        // 32 GB RAM = Forge (was Forge before too — by accident).
        assert_eq!(recommend_tier(&s2), Tier::Forge);
    }

    #[test]
    fn defaults_match_pre_detection_floor() {
        let c = TierConfig::defaults();
        assert_eq!(c.selected_tier, Tier::Spark);
        assert_eq!(c.detected_tier, Tier::Spark);
        assert_eq!(c.detected_at_ms, 0);
        assert!(!c.manual_override);
        assert!(c.hardware_snapshot.gpu.is_none());
    }

    #[test]
    fn tier_serialises_lowercase() {
        assert_eq!(serde_json::to_string(&Tier::Spark).unwrap(), "\"spark\"");
        assert_eq!(serde_json::to_string(&Tier::Flame).unwrap(), "\"flame\"");
        assert_eq!(serde_json::to_string(&Tier::Forge).unwrap(), "\"forge\"");
        let back: Tier = serde_json::from_str("\"forge\"").unwrap();
        assert_eq!(back, Tier::Forge);
    }

    #[test]
    fn tier_all_lists_three_in_order() {
        assert_eq!(Tier::ALL, &[Tier::Spark, Tier::Flame, Tier::Forge]);
    }

    #[test]
    fn load_or_default_when_missing_returns_defaults() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("missing.json");
        assert_eq!(load_or_default(&path), TierConfig::defaults());
    }

    #[test]
    fn save_then_load_roundtrips() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nested").join("tier.json");
        let mut original = TierConfig::defaults();
        original.selected_tier = Tier::Forge;
        original.detected_tier = Tier::Flame;
        original.detected_at_ms = 1_700_000_000_000;
        original.manual_override = true;
        save(&path, &original).expect("save");
        let loaded = load_or_default(&path);
        assert_eq!(loaded, original);
    }

    #[test]
    fn load_or_default_falls_back_on_malformed_json() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("tier.json");
        fs::write(&path, "not json at all").unwrap();
        assert_eq!(load_or_default(&path), TierConfig::defaults());
    }

    #[test]
    fn unknown_fields_are_silently_ignored_on_read() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("tier.json");
        fs::write(
            &path,
            r#"{
                "selected_tier": "flame",
                "future_knob": "experimental"
            }"#,
        )
        .unwrap();
        let c = load_or_default(&path);
        assert_eq!(c.selected_tier, Tier::Flame);
    }

    #[test]
    fn unknown_fields_dropped_on_rewrite() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("tier.json");
        fs::write(&path, r#"{ "future_knob": ["x"] }"#).unwrap();
        let loaded = load_or_default(&path);
        save(&path, &loaded).expect("rewrite");
        let rewritten = fs::read_to_string(&path).unwrap();
        assert!(rewritten.contains("\"selected_tier\""));
        assert!(!rewritten.contains("future_knob"));
    }

    #[test]
    fn config_path_for_lives_beside_app_data() {
        let dir = Path::new("/tmp/aether-test");
        let p = config_path_for(dir);
        assert_eq!(p, Path::new("/tmp/aether-test/tier.json"));
    }
}
