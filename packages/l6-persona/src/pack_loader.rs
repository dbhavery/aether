//! Persona-pack YAML loader.
//!
//! The shipped shell ships three hard-coded `PersonaProfile`s in
//! `apps/desktop/src-tauri/src/state.rs::default_catalog()`. That
//! forces a Rust rebuild for every persona tweak and a Rust author
//! for every contributor. This loader lets personas live as
//! `personas/*.yaml` files that the shell can scan at boot and merge
//! into its in-memory catalog.
//!
//! ## Schema
//!
//! One persona per file. Schema mirrors [`PersonaProfile`] directly
//! and is deliberately conservative — any field not listed here is
//! not accepted. Forward compatibility comes from adding optional
//! fields with explicit defaults, never from re-purposing existing
//! ones.
//!
//! ```yaml
//! id: "solstice"              # Required. Stable wire id.
//! version: 1                  # Required. Monotonic.
//! name: "Solstice"            # Required. Human-readable label.
//! description: "A steady hand for long projects."   # Required.
//! tone: "neutral"             # warm | neutral | formal
//! verbosity: "balanced"       # terse | balanced | verbose
//! stance: "balanced"          # cautious | balanced | bold
//! humor: "occasional"         # dry | occasional | playful
//! ```
//!
//! ## Error model
//!
//! Every failure mode is explicit:
//!
//! - `Io` — file could not be read.
//! - `Parse` — YAML parse / schema mismatch (wrong types, unknown
//!   field, missing required field).
//! - `DuplicateId` — two files declared the same `id` within a single
//!   load.
//!
//! This is an internal/advanced feature for now: no UI surface for
//! picking which files to load, no hot-reload, no signature check.
//! Those belong to the richer `PersonaPack` surface in
//! `docs/PERSONA-SCHEMA.md`.
//!
//! ## Forward compatibility
//!
//! Any new field added to this schema must be optional with a
//! documented default — YAML files in the wild are a contract we
//! cannot break. Validate this rule by preserving the
//! `yaml_missing_fields_errors_cleanly` regression test.

use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::compiler::PersonaId;
use crate::profile::{Humor, PersonaProfile, Stance, Tone, Verbosity};

/// On-disk persona-pack schema, v0. A one-to-one mapping of
/// [`PersonaProfile`] fields with the only transformation being a
/// lowercase-string representation of the enum dials, which matches
/// the existing `serde` derive and is what a human would write.
///
/// The struct is `#[serde(deny_unknown_fields)]` so a typo in a YAML
/// file surfaces as a `Parse` error rather than silent ignore.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PersonaPackFile {
    /// Stable wire id (e.g. `"solstice"`). Must be unique within a
    /// load.
    pub id: String,
    /// Monotonic version integer.
    pub version: u32,
    /// Display name.
    pub name: String,
    /// Short self-description.
    pub description: String,
    /// Tone dial.
    #[serde(default = "default_tone")]
    pub tone: Tone,
    /// Verbosity dial.
    #[serde(default = "default_verbosity")]
    pub verbosity: Verbosity,
    /// Risk stance.
    #[serde(default = "default_stance")]
    pub stance: Stance,
    /// Humor dial.
    #[serde(default = "default_humor")]
    pub humor: Humor,
}

fn default_tone() -> Tone {
    Tone::Neutral
}
fn default_verbosity() -> Verbosity {
    Verbosity::Balanced
}
fn default_stance() -> Stance {
    Stance::Balanced
}
fn default_humor() -> Humor {
    Humor::Occasional
}

impl PersonaPackFile {
    /// Lift the on-disk schema into the runtime [`PersonaProfile`].
    pub fn into_profile(self) -> PersonaProfile {
        PersonaProfile {
            persona_id: PersonaId(self.id),
            version: self.version,
            name: self.name,
            description: self.description,
            tone: self.tone,
            verbosity: self.verbosity,
            stance: self.stance,
            humor: self.humor,
        }
    }
}

/// Errors surfaced by the loader.
#[derive(Debug, Error)]
pub enum PackLoadError {
    /// Filesystem I/O failure — missing directory, unreadable file,
    /// permission denied.
    #[error("persona pack I/O error at {path:?}: {source}")]
    Io {
        /// Path we tried to read.
        path: PathBuf,
        /// Underlying error.
        #[source]
        source: std::io::Error,
    },
    /// YAML parse / schema validation failure.
    #[error("persona pack parse error at {path:?}: {source}")]
    Parse {
        /// Path that failed to parse.
        path: PathBuf,
        /// Underlying serde error.
        #[source]
        source: serde_yaml::Error,
    },
    /// Two files declared the same `id`.
    #[error("duplicate persona id {id:?}: first at {first:?}, duplicate at {duplicate:?}")]
    DuplicateId {
        /// The clashing id.
        id: String,
        /// Path that declared it first.
        first: PathBuf,
        /// Path that redeclared it.
        duplicate: PathBuf,
    },
}

/// Load and parse a single persona-pack YAML file.
pub fn load_pack_file(path: impl AsRef<Path>) -> Result<PersonaProfile, PackLoadError> {
    let path_ref = path.as_ref();
    let raw = fs::read_to_string(path_ref).map_err(|source| PackLoadError::Io {
        path: path_ref.to_path_buf(),
        source,
    })?;
    let file: PersonaPackFile =
        serde_yaml::from_str(&raw).map_err(|source| PackLoadError::Parse {
            path: path_ref.to_path_buf(),
            source,
        })?;
    Ok(file.into_profile())
}

/// Scan a directory for `*.yaml` / `*.yml` persona packs and return
/// the parsed profiles.
///
/// - Missing directory → `Ok(Vec::new())`. Treating "no pack dir" as
///   an empty pack set makes the loader safe to call unconditionally
///   on shell boot.
/// - Non-YAML files are ignored silently.
/// - On the first hard failure (`Io`, `Parse`, `DuplicateId`) the
///   function returns `Err`, so callers can choose between
///   all-or-nothing semantics and degraded-boot fallback.
pub fn load_pack_dir(dir: impl AsRef<Path>) -> Result<Vec<PersonaProfile>, PackLoadError> {
    let dir_ref = dir.as_ref();
    let rd = match fs::read_dir(dir_ref) {
        Ok(rd) => rd,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(source) => {
            return Err(PackLoadError::Io {
                path: dir_ref.to_path_buf(),
                source,
            })
        }
    };

    // Collect (id → path) for dup detection plus the profiles for
    // return. A sorted scan would be nicer than the OS-defined order
    // but the existing catalog doesn't promise order either; ship the
    // simple version.
    let mut out: Vec<PersonaProfile> = Vec::new();
    let mut seen: Vec<(String, PathBuf)> = Vec::new();

    for entry in rd {
        let entry = entry.map_err(|source| PackLoadError::Io {
            path: dir_ref.to_path_buf(),
            source,
        })?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
        if !matches!(ext, "yaml" | "yml") {
            continue;
        }
        let profile = load_pack_file(&path)?;
        let id = profile.persona_id.0.clone();
        if let Some((_, first)) = seen.iter().find(|(seen_id, _)| seen_id == &id) {
            return Err(PackLoadError::DuplicateId {
                id,
                first: first.clone(),
                duplicate: path,
            });
        }
        seen.push((id, path));
        out.push(profile);
    }

    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn write(tmp: &TempDir, name: &str, body: &str) -> PathBuf {
        let p = tmp.path().join(name);
        fs::write(&p, body).unwrap();
        p
    }

    const SOLSTICE_YAML: &str = r#"
id: "solstice"
version: 2
name: "Solstice"
description: "A steady hand for long projects."
tone: "neutral"
verbosity: "balanced"
stance: "balanced"
humor: "dry"
"#;

    #[test]
    fn valid_yaml_parses_to_persona_profile() {
        let tmp = TempDir::new().unwrap();
        let p = write(&tmp, "solstice.yaml", SOLSTICE_YAML);
        let profile = load_pack_file(&p).expect("parse");
        assert_eq!(profile.persona_id.0, "solstice");
        assert_eq!(profile.version, 2);
        assert_eq!(profile.name, "Solstice");
        assert_eq!(profile.tone, Tone::Neutral);
        assert_eq!(profile.humor, Humor::Dry);
    }

    #[test]
    fn load_pack_dir_returns_every_valid_file() {
        let tmp = TempDir::new().unwrap();
        let _a = write(&tmp, "a.yaml", SOLSTICE_YAML);
        let _b = write(
            &tmp,
            "b.yml",
            r#"
id: "nova"
version: 1
name: "Nova"
description: "Bright and decisive."
tone: "warm"
verbosity: "terse"
stance: "bold"
humor: "playful"
"#,
        );
        // Non-YAML file must be ignored.
        write(&tmp, "README.md", "not a persona");
        let profiles = load_pack_dir(tmp.path()).expect("load dir");
        assert_eq!(profiles.len(), 2);
        let mut ids: Vec<_> = profiles.iter().map(|p| p.persona_id.0.clone()).collect();
        ids.sort();
        assert_eq!(ids, vec!["nova".to_string(), "solstice".to_string()]);
    }

    #[test]
    fn missing_directory_is_empty_pack_set() {
        let tmp = TempDir::new().unwrap();
        let ghost = tmp.path().join("does-not-exist");
        assert!(load_pack_dir(&ghost).unwrap().is_empty());
    }

    #[test]
    fn duplicate_id_across_files_is_an_error() {
        let tmp = TempDir::new().unwrap();
        let _a = write(&tmp, "first.yaml", SOLSTICE_YAML);
        let _b = write(
            &tmp,
            "second.yaml",
            r#"
id: "solstice"
version: 9
name: "Solstice Alt"
description: "Clashing id."
tone: "neutral"
verbosity: "balanced"
stance: "balanced"
humor: "occasional"
"#,
        );
        let err = load_pack_dir(tmp.path()).unwrap_err();
        match err {
            PackLoadError::DuplicateId { id, .. } => assert_eq!(id, "solstice"),
            other => panic!("expected DuplicateId, got {other:?}"),
        }
    }

    #[test]
    fn yaml_missing_fields_errors_cleanly() {
        let tmp = TempDir::new().unwrap();
        // Missing `name` and `description` — both required on the
        // current schema. If we ever add defaults for them, THIS
        // regression must be updated deliberately and the docs kept
        // in sync.
        let p = write(
            &tmp,
            "broken.yaml",
            r#"
id: "broken"
version: 1
tone: "warm"
verbosity: "balanced"
stance: "balanced"
humor: "occasional"
"#,
        );
        match load_pack_file(&p) {
            Err(PackLoadError::Parse { .. }) => {}
            other => panic!("expected Parse error, got {other:?}"),
        }
    }

    #[test]
    fn unknown_fields_are_rejected() {
        let tmp = TempDir::new().unwrap();
        let p = write(
            &tmp,
            "typo.yaml",
            r#"
id: "typo"
version: 1
name: "Typo"
description: "extra field"
tonality: "warm"  # typo: should be "tone"
"#,
        );
        assert!(matches!(
            load_pack_file(&p),
            Err(PackLoadError::Parse { .. })
        ));
    }

    #[test]
    fn optional_dials_fall_back_to_defaults() {
        let tmp = TempDir::new().unwrap();
        let p = write(
            &tmp,
            "minimal.yaml",
            r#"
id: "minimal"
version: 1
name: "Minimal"
description: "Only required fields."
"#,
        );
        let profile = load_pack_file(&p).expect("minimal profile");
        assert_eq!(profile.tone, Tone::Neutral);
        assert_eq!(profile.verbosity, Verbosity::Balanced);
        assert_eq!(profile.stance, Stance::Balanced);
        assert_eq!(profile.humor, Humor::Occasional);
    }
}
