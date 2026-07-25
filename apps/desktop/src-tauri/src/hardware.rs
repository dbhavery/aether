//! ADR-0006 §Decision 2 — hardware detection.
//!
//! Pure read. Does not render, does not load models, does not allocate
//! GPU memory. Runs once at boot and again on explicit user "Re-detect
//! hardware" action. Output feeds tier auto-recommendation
//! (`tier::recommend_tier`) and onboarding affordances (disk-space
//! preflight, backfill latency estimates).
//!
//! ## Sources
//!
//! - **GPU adapter** via `wgpu::Instance::enumerate_adapters` —
//!   cross-platform Vulkan / Metal / DX12 / GLES coverage. We pick the
//!   highest-priority adapter (discrete > integrated > virtual > cpu)
//!   and read `AdapterInfo` + `Limits` from it.
//! - **System RAM / CPU cores** via `sysinfo`.
//! - **Disk available** via `std::fs::available_space` on the app-data
//!   directory.
//! - **Ollama GPU status** (optional) via a one-shot `GET /api/ps` —
//!   tells us whether the local Ollama daemon currently has any model
//!   resident in VRAM (validates the GPU path is wired end-to-end).
//!   No model loads triggered by this probe.
//!
//! ## VRAM estimation caveat
//!
//! `wgpu` does not expose total VRAM cross-platform; `Limits::max_buffer_size`
//! is a *single-allocation* ceiling, not a total. We treat it as a
//! conservative *lower bound* for VRAM. Tier auto-recommendation
//! consumes both the device type and the VRAM estimate, but device
//! type is the primary signal. The user-override path (ADR-0006 D5)
//! covers cases where heuristic detection picks wrong.
//!
//! Future enhancement: NVML on NVIDIA / IOKit on macOS feature-gated
//! probes can refine the estimate. Held for a future ADR — see
//! ADR-0006 §Open items.

use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

/// Coarse classification of the detected primary GPU. Mirrors
/// `wgpu::DeviceType` but flattens vendor/version specifics into a
/// stable wire shape for `tier.json`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GpuKind {
    /// Dedicated GPU on a discrete bus. Typical Flame / Forge tier.
    DiscreteGpu,
    /// GPU shares system memory with the CPU (laptop iGPU,
    /// Apple Silicon unified memory, AMD APU, Intel Arc Xe). Typical
    /// Spark tier.
    IntegratedGpu,
    /// VM-virtualised GPU (cloud, Parallels, etc.). Treated like a
    /// discrete device for tier purposes but flagged so the user can
    /// override.
    VirtualGpu,
    /// Software / CPU-only fallback adapter. Spark tier floor.
    Cpu,
    /// Backend reports a device wgpu does not classify (rare). Treated
    /// like Spark.
    Other,
}

impl GpuKind {
    /// Numeric priority used to pick the "best" adapter when multiple
    /// are exposed. Discrete wins over integrated; both win over
    /// virtual / cpu / other.
    fn priority(self) -> i64 {
        match self {
            GpuKind::DiscreteGpu => 1_000_000,
            GpuKind::IntegratedGpu => 500_000,
            GpuKind::VirtualGpu => 100,
            GpuKind::Cpu => 10,
            GpuKind::Other => 0,
        }
    }
}

/// Information about the chosen primary GPU. `None` at the
/// `HardwareSnapshot` level means no adapter was detected — extremely
/// rare in practice (even headless servers expose a CPU adapter
/// through wgpu). When present, every field is best-effort: vendors
/// expose different amounts of detail through different backends.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GpuInfo {
    /// Vendor id rendered as a hex string (e.g. `"0x10de"` for NVIDIA,
    /// `"0x1002"` for AMD, `"0x8086"` for Intel, `"0x106b"` for Apple).
    /// Hex form is used because wgpu reports vendors as numeric ids
    /// without a stable string mapping across backends.
    pub vendor_id: String,
    /// Device / adapter name as reported by the backend (e.g.
    /// `"NVIDIA GeForce RTX 4070"`).
    pub device_name: String,
    /// Coarse classification used by tier recommendation.
    pub kind: GpuKind,
    /// Backend wgpu used to enumerate this adapter (`"Vulkan"`,
    /// `"Metal"`, `"Dx12"`, `"Gl"`, etc.). Diagnostic only.
    pub backend: String,
    /// Conservative *lower-bound* VRAM estimate in GB, derived from
    /// `wgpu::Limits::max_buffer_size`. May significantly understate
    /// real VRAM (24 GB cards often report a 4 GB max-buffer-size on
    /// Vulkan). Tier recommendation treats this as a hint, not a
    /// truth.
    pub vram_gb_estimate: u32,
}

/// Full hardware snapshot, persisted into `tier.json` and consumed by
/// `tier::recommend_tier` plus onboarding surfaces.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct HardwareSnapshot {
    /// Best detected GPU (highest-priority adapter wgpu reported).
    /// `None` if wgpu enumeration failed entirely (driver-less
    /// container, etc.).
    pub gpu: Option<GpuInfo>,
    /// Total system RAM in GB (rounded down).
    pub total_ram_gb: u32,
    /// Logical CPU cores reported by `sysinfo`.
    pub cpu_cores: u32,
    /// Free space on the app-data directory in GB at detection time.
    /// `None` when no path was passed (e.g. tests) or the read
    /// failed.
    pub disk_available_gb: Option<u32>,
    /// `Some(true)` if Ollama's `/api/ps` reported at least one model
    /// resident with non-zero VRAM at detection time. `Some(false)`
    /// if the daemon is reachable but no model is GPU-loaded.
    /// `None` if Ollama is unreachable or no probe was attempted.
    pub ollama_gpu_loaded: Option<bool>,
    /// Wall-clock millis of detection. Surfaced in the Settings UI
    /// so users can see how recent the snapshot is.
    pub detected_at_ms: u64,
}

impl HardwareSnapshot {
    /// Empty snapshot used as the default before detection has run.
    /// Distinct from a "detection failed" snapshot — the latter has
    /// `detected_at_ms` set.
    pub fn unknown() -> Self {
        Self {
            gpu: None,
            total_ram_gb: 0,
            cpu_cores: 0,
            disk_available_gb: None,
            ollama_gpu_loaded: None,
            detected_at_ms: 0,
        }
    }
}

/// Run a full detection pass.
///
/// `app_data_dir` is used for the disk-space probe; pass `None` in
/// tests / sandboxes that don't have a writable data dir. `ollama_base_url`
/// is the base URL for the optional Ollama `/api/ps` probe; pass
/// `None` to skip (also used by tests).
///
/// Always returns a snapshot — detection failures degrade to
/// best-effort partial fields rather than erroring. The shell never
/// fails to boot because hardware probing returned no info.
pub fn detect(app_data_dir: Option<&Path>, ollama_base_url: Option<&str>) -> HardwareSnapshot {
    let gpu = detect_best_gpu();
    let (total_ram_gb, cpu_cores) = detect_cpu_ram();
    let disk_available_gb = app_data_dir.and_then(probe_disk_gb);
    let ollama_gpu_loaded = ollama_base_url.and_then(probe_ollama_gpu);

    HardwareSnapshot {
        gpu,
        total_ram_gb,
        cpu_cores,
        disk_available_gb,
        ollama_gpu_loaded,
        detected_at_ms: now_ms(),
    }
}

fn detect_best_gpu() -> Option<GpuInfo> {
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor::default());
    let adapters: Vec<wgpu::Adapter> = instance
        .enumerate_adapters(wgpu::Backends::all())
        .into_iter()
        .collect();

    if adapters.is_empty() {
        tracing::warn!("hardware detection: wgpu enumerated zero adapters");
        return None;
    }

    let mut best: Option<(i64, GpuInfo)> = None;
    for adapter in adapters {
        let info = adapter.get_info();
        let limits = adapter.limits();
        let kind = device_type_to_kind(info.device_type);
        let vram_gb_estimate = (limits.max_buffer_size / (1024 * 1024 * 1024)) as u32;
        let score = kind.priority() + vram_gb_estimate as i64;
        let gpu = GpuInfo {
            vendor_id: format!("{:#x}", info.vendor),
            device_name: info.name,
            kind,
            backend: format!("{:?}", info.backend),
            vram_gb_estimate,
        };
        match &best {
            None => best = Some((score, gpu)),
            Some((s, _)) if score > *s => best = Some((score, gpu)),
            _ => {}
        }
    }
    best.map(|(_, g)| g)
}

fn device_type_to_kind(t: wgpu::DeviceType) -> GpuKind {
    match t {
        wgpu::DeviceType::DiscreteGpu => GpuKind::DiscreteGpu,
        wgpu::DeviceType::IntegratedGpu => GpuKind::IntegratedGpu,
        wgpu::DeviceType::VirtualGpu => GpuKind::VirtualGpu,
        wgpu::DeviceType::Cpu => GpuKind::Cpu,
        wgpu::DeviceType::Other => GpuKind::Other,
    }
}

fn detect_cpu_ram() -> (u32, u32) {
    let mut sys = sysinfo::System::new();
    sys.refresh_memory();
    sys.refresh_cpu_usage();
    let total_ram_gb = (sys.total_memory() / (1024 * 1024 * 1024)) as u32;
    let cpu_cores = sys.cpus().len() as u32;
    (total_ram_gb, cpu_cores)
}

fn probe_disk_gb(path: &Path) -> Option<u32> {
    // Walk up to find an extant directory if the literal path doesn't
    // exist yet (first launch before app-data is created). NOTE: we
    // deliberately do NOT call `std::fs::canonicalize` here — on
    // Windows it returns paths with the `\\?\` extended-length
    // prefix, which `sysinfo::Disk::mount_point()` does not produce,
    // and `starts_with` then fails to match the drive root.
    let mut p = path.to_path_buf();
    while !p.exists() {
        match p.parent() {
            Some(parent) => p = parent.to_path_buf(),
            None => return None,
        }
    }

    // Pick the longest-mount-point disk whose mount is a prefix of our
    // path. On Windows, that's the drive letter root. On unix, the
    // most-specific mount point (handles bind mounts and per-dir
    // mounts gracefully).
    let disks = sysinfo::Disks::new_with_refreshed_list();
    let mut best: Option<(usize, u64)> = None;
    for d in disks.list() {
        let mp = d.mount_point();
        if p.starts_with(mp) {
            let mp_len = mp.as_os_str().len();
            let avail = d.available_space();
            match best {
                None => best = Some((mp_len, avail)),
                Some((l, _)) if mp_len > l => best = Some((mp_len, avail)),
                _ => {}
            }
        }
    }
    best.map(|(_, bytes)| (bytes / (1024 * 1024 * 1024)) as u32)
}

fn probe_ollama_gpu(base_url: &str) -> Option<bool> {
    let url = format!("{}/api/ps", base_url.trim_end_matches('/'));
    let agent = ureq::AgentBuilder::new()
        .timeout(Duration::from_millis(750))
        .build();
    let resp = match agent.get(&url).call() {
        Ok(r) => r,
        Err(e) => {
            tracing::debug!("ollama /api/ps probe failed (daemon unreachable?): {e}");
            return None;
        }
    };
    let json: serde_json::Value = match resp.into_json() {
        Ok(j) => j,
        Err(e) => {
            tracing::warn!("ollama /api/ps non-json response: {e}");
            return None;
        }
    };
    let arr = json.get("models").and_then(|v| v.as_array())?;
    // Any model with size_vram > 0 means a model is GPU-resident.
    let any_gpu = arr.iter().any(|m| {
        m.get("size_vram")
            .and_then(|v| v.as_u64())
            .map(|n| n > 0)
            .unwrap_or(false)
    });
    Some(any_gpu)
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn gpu_kind_priority_orders_correctly() {
        assert!(GpuKind::DiscreteGpu.priority() > GpuKind::IntegratedGpu.priority());
        assert!(GpuKind::IntegratedGpu.priority() > GpuKind::VirtualGpu.priority());
        assert!(GpuKind::VirtualGpu.priority() > GpuKind::Cpu.priority());
        assert!(GpuKind::Cpu.priority() > GpuKind::Other.priority());
    }

    #[test]
    fn snapshot_unknown_zeroes_everything() {
        let s = HardwareSnapshot::unknown();
        assert!(s.gpu.is_none());
        assert_eq!(s.total_ram_gb, 0);
        assert_eq!(s.cpu_cores, 0);
        assert!(s.disk_available_gb.is_none());
        assert!(s.ollama_gpu_loaded.is_none());
        assert_eq!(s.detected_at_ms, 0);
    }

    #[test]
    fn detect_runs_to_completion_in_ci_sandbox() {
        // Detection must always return a snapshot, never panic. Even in
        // environments where wgpu can't enumerate (CI containers, etc.)
        // the Cpu fallback adapter is exposed by every wgpu backend, so
        // gpu is usually Some. Either way, total_ram_gb / cpu_cores
        // populate from sysinfo.
        let s = detect(None, None);
        assert!(s.detected_at_ms > 0, "detection must stamp a timestamp");
        assert!(s.cpu_cores > 0, "sysinfo always reports >=1 core");
        assert!(
            s.disk_available_gb.is_none(),
            "no path passed; disk probe skipped"
        );
        assert!(
            s.ollama_gpu_loaded.is_none(),
            "no base_url passed; ollama probe skipped"
        );
    }

    #[test]
    fn detect_with_app_data_path_probes_disk() {
        let tmp = TempDir::new().unwrap();
        let s = detect(Some(tmp.path()), None);
        // disk_available_gb may legitimately be 0 in tight CI envs but
        // should be Some(_). On a developer box it will be a real value.
        assert!(s.disk_available_gb.is_some(), "disk probe should run");
    }

    #[test]
    fn detect_skips_ollama_when_unreachable_url() {
        // Hit a port nothing listens on. Probe must not panic, must
        // return None, must not hang the detection.
        let s = detect(None, Some("http://127.0.0.1:1"));
        assert!(s.ollama_gpu_loaded.is_none());
    }

    #[test]
    fn snapshot_round_trips_through_serde() {
        let s = HardwareSnapshot {
            gpu: Some(GpuInfo {
                vendor_id: "0x10de".into(),
                device_name: "NVIDIA GeForce RTX 4070".into(),
                kind: GpuKind::DiscreteGpu,
                backend: "Vulkan".into(),
                vram_gb_estimate: 12,
            }),
            total_ram_gb: 32,
            cpu_cores: 16,
            disk_available_gb: Some(500),
            ollama_gpu_loaded: Some(true),
            detected_at_ms: 1_700_000_000_000,
        };
        let json = serde_json::to_string(&s).expect("serialize");
        let back: HardwareSnapshot = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back, s);
    }

    #[test]
    fn gpu_kind_serialises_snake_case() {
        let k = GpuKind::DiscreteGpu;
        let s = serde_json::to_string(&k).unwrap();
        assert_eq!(s, "\"discrete_gpu\"");
        let back: GpuKind = serde_json::from_str("\"integrated_gpu\"").unwrap();
        assert_eq!(back, GpuKind::IntegratedGpu);
    }
}
