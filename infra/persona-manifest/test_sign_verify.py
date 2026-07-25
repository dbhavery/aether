"""End-to-end test for the keygen → sign → verify pipeline.

Locks the contract between sign_manifest.py and verify_manifest.py
without requiring Don's real release key. Each test gets its own
tempdir and disposable key pair so runs are isolated.

Run: python -m pytest infra/persona-manifest/test_sign_verify.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
KEYGEN = REPO_ROOT / "infra" / "persona-manifest" / "keygen.py"
SIGN = REPO_ROOT / "infra" / "persona-manifest" / "sign_manifest.py"
VERIFY = REPO_ROOT / "infra" / "persona-manifest" / "verify_manifest.py"


def _fixture_manifest() -> dict:
    return {
        "schema_version": 1,
        "generated": "2026-04-29T00:00:00Z",
        "manifest_version": "0.0.1",
        "signature": None,
        "personas": [
            {
                "slug": "alice",
                "version": "1.0.0",
                "display_name": "Alice",
                "archetype": "warm_supportive",
                "size_bytes": 1234,
                "shared_deps": [],
                "asset_url": "https://example/test/alice-1.0.0.zip",
                "sha256": "a" * 64,
            },
            {
                "slug": "bob",
                "version": "1.0.0",
                "display_name": "Bob",
                "archetype": "analytical_focused",
                "size_bytes": 5678,
                "shared_deps": [],
                "asset_url": "https://example/test/bob-1.0.0.zip",
                "sha256": "b" * 64,
            },
        ],
    }


def _run(*args: str | Path, expect_ok: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [sys.executable, *map(str, args)], capture_output=True, text=True
    )
    if expect_ok and result.returncode != 0:
        pytest.fail(
            f"command failed (exit {result.returncode}):\n"
            f"  stdout: {result.stdout}\n  stderr: {result.stderr}"
        )
    return result


def test_keygen_produces_three_files(tmp_path: Path):
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    assert (out / "aether-release-ed25519.sk").is_file()
    assert (out / "aether-release-ed25519.pk").is_file()
    assert (out / "aether-release-ed25519.pk.b64").is_file()
    assert len((out / "aether-release-ed25519.sk").read_bytes()) == 32
    assert len((out / "aether-release-ed25519.pk").read_bytes()) == 32


def test_keygen_refuses_to_overwrite_without_force(tmp_path: Path):
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    again = _run(KEYGEN, "--out-dir", out, expect_ok=False)
    assert again.returncode != 0
    assert "refusing to overwrite" in again.stderr


def test_keygen_force_rotates(tmp_path: Path):
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    sk_before = (out / "aether-release-ed25519.sk").read_bytes()
    _run(KEYGEN, "--out-dir", out, "--force")
    sk_after = (out / "aether-release-ed25519.sk").read_bytes()
    assert sk_before != sk_after, "force should generate a different key"


def test_sign_then_verify_round_trips(tmp_path: Path):
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    sk = out / "aether-release-ed25519.sk"
    pk = out / "aether-release-ed25519.pk"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_fixture_manifest()), encoding="utf-8")

    _run(SIGN, "--in", manifest_path, "--sk", sk)
    signed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(signed["signature"], str)
    assert signed["signature"].startswith("ed25519:")

    _run(VERIFY, "--in", manifest_path, "--pk", pk)


def test_verify_fails_when_personas_array_tampered(tmp_path: Path):
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    sk = out / "aether-release-ed25519.sk"
    pk = out / "aether-release-ed25519.pk"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_fixture_manifest()), encoding="utf-8")
    _run(SIGN, "--in", manifest_path, "--sk", sk)

    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["personas"][0]["sha256"] = "f" * 64  # flip a hash
    manifest_path.write_text(json.dumps(tampered), encoding="utf-8")

    result = _run(VERIFY, "--in", manifest_path, "--pk", pk, expect_ok=False)
    assert result.returncode != 0
    assert "signature does not match" in result.stderr


def test_verify_passes_when_only_wrapper_metadata_changes(tmp_path: Path):
    """The signature covers the personas array, not the wrapper.

    Signers are free to update `generated` / `manifest_version` on
    the wrapper post-sign without invalidating the signature.
    """
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    sk = out / "aether-release-ed25519.sk"
    pk = out / "aether-release-ed25519.pk"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_fixture_manifest()), encoding="utf-8")
    _run(SIGN, "--in", manifest_path, "--sk", sk)

    same_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    same_payload["generated"] = "2099-01-01T00:00:00Z"
    same_payload["manifest_version"] = "9.9.9"
    manifest_path.write_text(json.dumps(same_payload), encoding="utf-8")

    _run(VERIFY, "--in", manifest_path, "--pk", pk)


def test_sign_refuses_to_resign_without_flag(tmp_path: Path):
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    sk = out / "aether-release-ed25519.sk"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_fixture_manifest()), encoding="utf-8")
    _run(SIGN, "--in", manifest_path, "--sk", sk)
    again = _run(SIGN, "--in", manifest_path, "--sk", sk, expect_ok=False)
    assert again.returncode != 0
    assert "already carries a signature" in again.stderr


def test_sign_allows_resign_with_flag(tmp_path: Path):
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    sk = out / "aether-release-ed25519.sk"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_fixture_manifest()), encoding="utf-8")
    _run(SIGN, "--in", manifest_path, "--sk", sk)
    _run(SIGN, "--in", manifest_path, "--sk", sk, "--allow-resign")


def test_verify_with_pk_b64_alternative(tmp_path: Path):
    out = tmp_path / "keys"
    _run(KEYGEN, "--out-dir", out)
    sk = out / "aether-release-ed25519.sk"
    pk_b64 = (out / "aether-release-ed25519.pk.b64").read_text().strip()

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_fixture_manifest()), encoding="utf-8")
    _run(SIGN, "--in", manifest_path, "--sk", sk)
    _run(VERIFY, "--in", manifest_path, "--pk-b64", pk_b64)
