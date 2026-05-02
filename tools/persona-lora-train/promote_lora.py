"""Promote a trained LoRA adapter into the persona's loras/ directory.

Atomic move + naming convention + sha256 manifest. Replaces the manual
`mv build/lora-train/aurora-v1/output/pytorch_lora_weights.safetensors
personas/aurora/loras/aurora_v1.safetensors` pattern with a tool that:

  - Walks the training output_dir for `pytorch_lora_weights.safetensors`
  - Copies (not moves) to `personas/<slug>/loras/<persona>_<version>.safetensors`
  - Writes a sibling `<file>.meta.json` with sha256, source path, training
    metadata (rank, steps, base_model) extracted from the training_config.json
  - Verifies the destination exists + matches the source byte-for-byte
    (paranoid copy, not a renaming rename — keeps the original around in
    case verify_lora rejects)

Usage:

    python tools/persona-lora-train/promote_lora.py \\
      --persona aurora \\
      --workdir build/lora-train/aurora-v1 \\
      --version v1

After successful promotion, `pipeline_status.py` reports
`LoRA on disk: yes` for the persona and the LoRA can be loaded by
`backend_local_flux.generate(lora_path=...)`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_training_config(workdir: Path) -> dict:
    config_path = workdir / "training_config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def promote(
    *,
    persona_slug: str,
    workdir: Path,
    version: str,
    repo_root: Path,
) -> Path:
    """Copy the trained adapter to personas/<slug>/loras/. Returns dest path.

    Raises FileNotFoundError if no adapter is found, ValueError if dest
    already exists with different content (refuse to overwrite).
    """
    output_dir = workdir / "output"
    src = output_dir / "pytorch_lora_weights.safetensors"
    if not src.exists():
        # Maybe the diffusers script wrote a different basename.
        candidates = sorted(output_dir.glob("*.safetensors"))
        if len(candidates) == 1:
            src = candidates[0]
        else:
            raise FileNotFoundError(
                f"no adapter found in {output_dir} "
                f"(checked pytorch_lora_weights.safetensors and *.safetensors)"
            )

    src_sha = _hash_file(src)

    loras_dir = repo_root / "personas" / persona_slug / "loras"
    loras_dir.mkdir(parents=True, exist_ok=True)
    dest = loras_dir / f"{persona_slug}_{version}.safetensors"

    if dest.exists():
        existing_sha = _hash_file(dest)
        if existing_sha == src_sha:
            print(f"[promote] dest already up-to-date: {dest}")
            return dest
        raise ValueError(
            f"refuse to overwrite {dest} — existing sha256 differs from source. "
            "Pick a different --version or remove the old file first."
        )

    shutil.copy2(src, dest)

    # Verify byte-for-byte after copy — paranoid, but cheap insurance.
    if _hash_file(dest) != src_sha:
        dest.unlink()
        raise IOError(
            f"copy verification failed: dest sha256 != src sha256. "
            "Aborted; dest removed."
        )

    # Sidecar metadata.
    config = _read_training_config(workdir)
    hyperparams = config.get("hyperparams", {})
    meta = {
        "schema_version": 1,
        "persona_slug": persona_slug,
        "version": version,
        "promoted_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_path": str(src.as_posix()),
        "source_workdir": str(workdir.as_posix()),
        "sha256": src_sha,
        "base_model": hyperparams.get("base_model"),
        "rank": hyperparams.get("rank"),
        "max_train_steps": hyperparams.get("max_train_steps"),
        "learning_rate": hyperparams.get("learning_rate"),
        "resolution": hyperparams.get("resolution"),
        "instance_token": config.get("instance_token"),
        "num_training_images": config.get("num_training_images"),
    }
    meta_path = dest.with_suffix(dest.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[promote] {persona_slug}/{version}: {src} -> {dest}")
    print(f"[promote] sha256={src_sha}")
    print(f"[promote] meta sidecar: {meta_path}")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="promote-lora")
    parser.add_argument("--persona", required=True)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument(
        "--version",
        required=True,
        help="version tag (e.g. 'v1' or '2026-05-02')",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="defaults to the file's grandparent (repo root)",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root or Path(__file__).resolve().parents[2]
    try:
        promote(
            persona_slug=args.persona,
            workdir=args.workdir.resolve(),
            version=args.version,
            repo_root=repo_root,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"[promote] FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
