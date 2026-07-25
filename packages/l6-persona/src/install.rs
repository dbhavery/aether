//! Persona-pack install primitives — local file ops only.
//!
//! ADR-0012 specifies a Tier-2 download-on-demand persona delivery
//! model. The HTTP fetch and Ed25519 manifest verification belong to
//! upstream layers (the desktop shell + L5 policy gates); this module
//! covers everything the L6 persona layer can do without a network:
//!
//! - [`verify_zip_sha256`] — confirm a downloaded zip matches the
//!   manifest's claimed digest before any extraction.
//! - [`extract_pack_zip`] — unpack a verified zip into the user's
//!   `<app_data>/personas/<slug>/` directory, refusing path
//!   traversal.
//! - [`uninstall_pack`] — remove a previously-extracted pack.
//! - [`read_current_persona`] / [`write_current_persona`] — durable
//!   "which companion did the user pick last?" pointer, persisted as
//!   a JSON file rather than in SQLite so it survives a corrupt-db
//!   recovery.
//!
//! The higher-level "atomic uninstall-then-install" switch flow from
//! ADR-0012 §Switch flow is composed by callers (the desktop shell)
//! using these primitives + an L5 policy ticket.
//!
//! # Threat model
//!
//! - **Malicious zip path traversal:** `..` segments and absolute
//!   paths in zip entries are rejected. A bad zip cannot escape the
//!   destination directory.
//! - **Truncated download:** SHA-256 mismatch fails fast; no
//!   extraction is attempted.
//! - **Half-extracted pack on crash:** extraction goes to a
//!   `.partial` sibling and is renamed to the final dir on success.
//!   A crash mid-extract leaves only the `.partial` dir which the
//!   next install attempt removes before retrying.
//! - **Concurrent install of the same slug:** not protected here.
//!   Caller (the desktop shell) is single-writer per the engine's
//!   single-writer rule (`aether/CLAUDE.md` §6).

use std::fs;
use std::io;
use std::io::Read;
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::compiler::PersonaId;

/// Errors surfaced by the install primitives.
#[derive(Debug, Error)]
pub enum InstallError {
    /// Filesystem I/O failure.
    #[error("install I/O error at {path:?}: {source}")]
    Io {
        /// Path the I/O was attempted on.
        path: PathBuf,
        /// Underlying error.
        #[source]
        source: io::Error,
    },
    /// SHA-256 of the downloaded zip didn't match the manifest claim.
    #[error("sha256 mismatch: expected {expected:?}, got {actual:?}")]
    Sha256Mismatch {
        /// Manifest-declared SHA-256 (lowercase hex, 64 chars).
        expected: String,
        /// Hash computed from the actual file bytes.
        actual: String,
    },
    /// Zip parse / decompression failure.
    #[error("zip read error at {path:?}: {source}")]
    Zip {
        /// Zip path being read.
        path: PathBuf,
        /// Underlying error.
        #[source]
        source: zip::result::ZipError,
    },
    /// Zip entry tried to escape the destination directory.
    #[error("zip path traversal rejected: entry {entry:?} resolves outside dest")]
    PathTraversal {
        /// The offending entry name from the zip.
        entry: String,
    },
    /// Pack directory already exists at the target slug.
    #[error("pack {slug:?} already installed at {path:?}")]
    AlreadyInstalled {
        /// Slug whose dir conflicted.
        slug: String,
        /// The conflicting path.
        path: PathBuf,
    },
    /// Pack directory missing for an uninstall request.
    #[error("pack {slug:?} not installed (no dir at {path:?})")]
    NotInstalled {
        /// Slug whose dir was expected.
        slug: String,
        /// Path that was missing.
        path: PathBuf,
    },
    /// Current-persona state file is malformed.
    #[error("current-persona state at {path:?} is malformed: {reason}")]
    StateMalformed {
        /// State file path.
        path: PathBuf,
        /// Why it failed to parse.
        reason: String,
    },
}

impl InstallError {
    fn io(path: impl Into<PathBuf>, source: io::Error) -> Self {
        Self::Io {
            path: path.into(),
            source,
        }
    }
}

/// Compute SHA-256 of a file and compare against the manifest claim.
///
/// Reads the file in 64 KiB chunks so a multi-MB zip doesn't allocate
/// a peak buffer larger than the chunk. Returns `Ok(())` on match,
/// `Err(Sha256Mismatch)` on any difference (case-insensitive on hex).
pub fn verify_zip_sha256(zip_path: &Path, expected_hex: &str) -> Result<(), InstallError> {
    let mut hasher = Sha256::new();
    let mut f = fs::File::open(zip_path).map_err(|e| InstallError::io(zip_path, e))?;
    let mut buf = [0u8; 65536];
    loop {
        let n = f
            .read(&mut buf)
            .map_err(|e| InstallError::io(zip_path, e))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    let got = format!("{:x}", hasher.finalize());
    let expected = expected_hex.trim().to_ascii_lowercase();
    if got != expected {
        return Err(InstallError::Sha256Mismatch {
            expected: expected_hex.to_string(),
            actual: got,
        });
    }
    Ok(())
}

/// Extract a verified persona-pack zip into `dest_dir/<slug>/`.
///
/// Refuses path traversal: any zip entry whose normalized path
/// contains a parent-dir (`..`) component or has an absolute prefix
/// is rejected before any byte is written. A successful extraction
/// produces a directory tree under `dest_dir/<slug>/` matching the
/// zip's internal layout.
///
/// Crash safety: extraction targets `dest_dir/<slug>.partial/` and
/// is renamed to `dest_dir/<slug>/` only after every entry writes
/// cleanly. A crash mid-extraction leaves only the `.partial` dir
/// which the next call removes before retrying.
///
/// Returns the final extraction path on success.
pub fn extract_pack_zip(
    zip_path: &Path,
    dest_dir: &Path,
    slug: &str,
) -> Result<PathBuf, InstallError> {
    let final_dir = dest_dir.join(slug);
    if final_dir.exists() {
        return Err(InstallError::AlreadyInstalled {
            slug: slug.to_string(),
            path: final_dir,
        });
    }
    let partial_dir = dest_dir.join(format!("{slug}.partial"));
    // Wipe any leftover partial from a prior crash.
    if partial_dir.exists() {
        fs::remove_dir_all(&partial_dir).map_err(|e| InstallError::io(&partial_dir, e))?;
    }
    fs::create_dir_all(&partial_dir).map_err(|e| InstallError::io(&partial_dir, e))?;

    let f = fs::File::open(zip_path).map_err(|e| InstallError::io(zip_path, e))?;
    let mut archive = zip::ZipArchive::new(f).map_err(|e| InstallError::Zip {
        path: zip_path.to_path_buf(),
        source: e,
    })?;
    for i in 0..archive.len() {
        let mut entry = archive.by_index(i).map_err(|e| InstallError::Zip {
            path: zip_path.to_path_buf(),
            source: e,
        })?;
        // Use the safer enclosed_name accessor so absolute paths and
        // `..` segments are caught up front. zip-rs returns None
        // when the path is unsafe; we treat that as a hard fail.
        let entry_name = entry.name().to_string();
        let Some(rel) = entry.enclosed_name() else {
            // Cleanup partial before bailing.
            let _ = fs::remove_dir_all(&partial_dir);
            return Err(InstallError::PathTraversal { entry: entry_name });
        };
        if rel.components().any(|c| matches!(c, Component::ParentDir)) {
            let _ = fs::remove_dir_all(&partial_dir);
            return Err(InstallError::PathTraversal { entry: entry_name });
        }
        let target = partial_dir.join(&rel);
        if entry.is_dir() {
            fs::create_dir_all(&target).map_err(|e| InstallError::io(&target, e))?;
            continue;
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|e| InstallError::io(parent, e))?;
        }
        let mut out = fs::File::create(&target).map_err(|e| InstallError::io(&target, e))?;
        io::copy(&mut entry, &mut out).map_err(|e| InstallError::io(&target, e))?;
    }
    fs::rename(&partial_dir, &final_dir).map_err(|e| InstallError::io(&final_dir, e))?;
    Ok(final_dir)
}

/// Remove a previously-extracted pack directory.
///
/// Idempotent only at the slug level — calling twice will return
/// [`InstallError::NotInstalled`] the second time. Callers that
/// need idempotency should match-and-discard `NotInstalled`.
pub fn uninstall_pack(dest_dir: &Path, slug: &str) -> Result<(), InstallError> {
    let dir = dest_dir.join(slug);
    if !dir.exists() {
        return Err(InstallError::NotInstalled {
            slug: slug.to_string(),
            path: dir,
        });
    }
    fs::remove_dir_all(&dir).map_err(|e| InstallError::io(&dir, e))?;
    Ok(())
}

/// Persistent "which companion is currently selected" pointer.
///
/// Stored as JSON rather than in the engine's SQLite so it survives
/// a corrupt-db recovery and remains readable by external tooling.
/// Single field for forward compatibility — adding fields here is
/// a non-breaking change because we use `serde(default)` on every
/// new field.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CurrentPersonaState {
    /// Slug of the currently-selected persona.
    pub current: PersonaId,
}

/// Read the current-persona pointer.
///
/// Returns `Ok(None)` when the file is missing (first-launch case);
/// returns [`InstallError::StateMalformed`] when the file exists
/// but parses as something else. Callers should treat the missing
/// case as "no selection yet" and surface the wizard.
pub fn read_current_persona(
    state_path: &Path,
) -> Result<Option<CurrentPersonaState>, InstallError> {
    match fs::read(state_path) {
        Ok(bytes) => {
            let parsed: CurrentPersonaState =
                serde_json::from_slice(&bytes).map_err(|e| InstallError::StateMalformed {
                    path: state_path.to_path_buf(),
                    reason: e.to_string(),
                })?;
            Ok(Some(parsed))
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(InstallError::io(state_path, e)),
    }
}

/// Atomically write the current-persona pointer.
///
/// Writes to `<state_path>.tmp` then renames so a crash mid-write
/// leaves the prior pointer intact. Creates parent directories on
/// demand.
pub fn write_current_persona(
    state_path: &Path,
    state: &CurrentPersonaState,
) -> Result<(), InstallError> {
    if let Some(parent) = state_path.parent() {
        fs::create_dir_all(parent).map_err(|e| InstallError::io(parent, e))?;
    }
    let tmp = state_path.with_extension("json.tmp");
    let body = serde_json::to_vec_pretty(state).map_err(|e| InstallError::StateMalformed {
        path: state_path.to_path_buf(),
        reason: e.to_string(),
    })?;
    fs::write(&tmp, body).map_err(|e| InstallError::io(&tmp, e))?;
    fs::rename(&tmp, state_path).map_err(|e| InstallError::io(state_path, e))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;
    use zip::write::SimpleFileOptions;

    fn write_zip(zip_path: &Path, entries: &[(&str, &[u8])]) {
        let f = fs::File::create(zip_path).expect("create zip");
        let mut w = zip::ZipWriter::new(f);
        let opts =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for (name, body) in entries {
            w.start_file(*name, opts).expect("start_file");
            w.write_all(body).expect("write zip body");
        }
        w.finish().expect("finish zip");
    }

    fn sha256_of(path: &Path) -> String {
        let mut h = Sha256::new();
        h.update(fs::read(path).unwrap());
        format!("{:x}", h.finalize())
    }

    #[test]
    fn sha256_match_passes_and_mismatch_fails() {
        let tmp = TempDir::new().unwrap();
        let zip = tmp.path().join("p.zip");
        write_zip(&zip, &[("a.yaml", b"id: a\n")]);
        let real = sha256_of(&zip);
        verify_zip_sha256(&zip, &real).expect("matching sha should pass");
        let err = verify_zip_sha256(&zip, "0".repeat(64).as_str()).unwrap_err();
        assert!(matches!(err, InstallError::Sha256Mismatch { .. }));
    }

    #[test]
    fn extract_unpacks_zip_and_atomic_renames_partial() {
        let tmp = TempDir::new().unwrap();
        let zip = tmp.path().join("alice.zip");
        write_zip(
            &zip,
            &[
                ("alice/persona.yaml", b"id: alice\n"),
                ("alice/avatar/anchor.png", b"\x89PNG\r\n\x1a\n..."),
            ],
        );
        let dest = tmp.path().join("install");
        let result = extract_pack_zip(&zip, &dest, "alice").expect("extract");
        assert_eq!(result, dest.join("alice"));
        assert!(dest.join("alice/alice/persona.yaml").exists());
        assert!(!dest.join("alice.partial").exists());
    }

    #[test]
    fn extract_refuses_path_traversal_via_parent_dir() {
        let tmp = TempDir::new().unwrap();
        let zip = tmp.path().join("evil.zip");
        write_zip(&zip, &[("../../etc/passwd", b"pwned")]);
        let dest = tmp.path().join("install");
        let err = extract_pack_zip(&zip, &dest, "alice").unwrap_err();
        assert!(matches!(err, InstallError::PathTraversal { .. }));
        // No leftover partial dir.
        assert!(!dest.join("alice.partial").exists());
        assert!(!dest.join("alice").exists());
    }

    #[test]
    fn extract_refuses_already_installed_slug() {
        let tmp = TempDir::new().unwrap();
        let zip = tmp.path().join("p.zip");
        write_zip(&zip, &[("alice/x.yaml", b"id: alice\n")]);
        let dest = tmp.path().join("install");
        extract_pack_zip(&zip, &dest, "alice").expect("first install");
        let err = extract_pack_zip(&zip, &dest, "alice").unwrap_err();
        assert!(matches!(err, InstallError::AlreadyInstalled { .. }));
    }

    #[test]
    fn extract_recovers_from_leftover_partial_dir() {
        // Simulates: previous extract crashed mid-way, leaving an
        // .partial dir. The next call should wipe it and re-extract
        // cleanly rather than fail.
        let tmp = TempDir::new().unwrap();
        let zip = tmp.path().join("p.zip");
        write_zip(&zip, &[("alice/x.yaml", b"id: alice\n")]);
        let dest = tmp.path().join("install");
        let stale_partial = dest.join("alice.partial");
        fs::create_dir_all(&stale_partial).unwrap();
        fs::write(stale_partial.join("stale.txt"), b"old").unwrap();

        extract_pack_zip(&zip, &dest, "alice").expect("recovery extract");
        assert!(dest.join("alice/alice/x.yaml").exists());
        assert!(!dest.join("alice.partial").exists());
    }

    #[test]
    fn uninstall_removes_dir_and_errors_when_missing() {
        let tmp = TempDir::new().unwrap();
        let zip = tmp.path().join("p.zip");
        write_zip(&zip, &[("alice/x.yaml", b"id: alice\n")]);
        let dest = tmp.path().join("install");
        extract_pack_zip(&zip, &dest, "alice").unwrap();
        assert!(dest.join("alice").exists());
        uninstall_pack(&dest, "alice").expect("uninstall");
        assert!(!dest.join("alice").exists());
        let err = uninstall_pack(&dest, "alice").unwrap_err();
        assert!(matches!(err, InstallError::NotInstalled { .. }));
    }

    #[test]
    fn current_persona_round_trips_and_is_atomic_on_write() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("nested/state/current.json");
        // First read on a missing file → None, no error.
        assert_eq!(read_current_persona(&path).unwrap(), None);

        let s = CurrentPersonaState {
            current: PersonaId("aurora".into()),
        };
        write_current_persona(&path, &s).expect("write");
        assert_eq!(read_current_persona(&path).unwrap(), Some(s));
        // No leftover .tmp file from the atomic rename.
        let tmp_path = path.with_extension("json.tmp");
        assert!(!tmp_path.exists(), "tmp shadow should be cleaned by rename");
    }

    #[test]
    fn current_persona_malformed_file_surfaces_state_malformed() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("current.json");
        fs::write(&path, b"this is not json").unwrap();
        let err = read_current_persona(&path).unwrap_err();
        assert!(matches!(err, InstallError::StateMalformed { .. }));
    }
}
