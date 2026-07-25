"""Source, trim, and normalise a CC0 / public-domain voice recording.

Usage:
    python scripts/persona_generator/source_voice.py <persona_id> \
        --url <mp3_or_wav_url> \
        [--start-sec 5] [--reference-sec 20] [--sample-sec 4]

Downloads the audio at `--url`, trims out:
    1. A `--reference-sec` clip (default 20s) starting `--start-sec` in,
       written to `personas/<id>/voice/reference.wav` (24kHz mono WAV).
    2. A `--sample-sec` clip (default 4s) starting `--start-sec` + 2s in,
       written to `personas/<id>/voice/sample.wav` (24kHz mono WAV).

The loader's schema §5 requires 5s <= reference.wav <= 60s — 20s is a
safe default that gives Chatterbox plenty to clone from without bloating
disk size.

Source attribution (URL, license, reader) is written to a
`voice/SOURCE.md` note; the operator then fills `metadata.yaml` with the
same info before shipping.

Runtime dependency: ffmpeg must be on PATH. Works offline once the file
is downloaded.

PREFERRED SOURCES (pick from these for new packs):
    * https://librivox.org/ — all recordings public domain (no rights)
    * https://commonvoice.mozilla.org/ — CC0 voice clips
    * https://freesound.org/ — filter by CC0 license, voice-over category
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]


def source(
    persona_id: str,
    url: str,
    *,
    start_sec: float = 5.0,
    reference_sec: float = 20.0,
    sample_sec: float = 4.0,
    force: bool = False,
) -> tuple[Path, Path]:
    if reference_sec < 5.0 or reference_sec > 60.0:
        raise SystemExit(
            f"reference_sec {reference_sec}s must be 5-60 (schema §5)"
        )
    if sample_sec < 1.0 or sample_sec > 10.0:
        raise SystemExit(f"sample_sec {sample_sec}s must be 1-10")

    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH — install ffmpeg first")

    voice_dir = _REPO_ROOT / "personas" / persona_id / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    reference = voice_dir / "reference.wav"
    sample = voice_dir / "sample.wav"
    if (reference.exists() or sample.exists()) and not force:
        print(
            f"[{persona_id}] voice files already exist — pass --force to overwrite"
        )
        return reference, sample

    # Download to a temp file; ffmpeg handles format conversion.
    suffix = ".mp3" if url.lower().endswith(".mp3") else ".audio"
    source_path = voice_dir / f".__source__{suffix}"
    print(f"[{persona_id}] downloading {url} …")
    _download(url, source_path)

    print(f"[{persona_id}] extracting reference ({reference_sec}s @ 24kHz mono) …")
    _ffmpeg_trim(source_path, reference, start=start_sec, duration=reference_sec)

    # Sample starts a bit after the reference's start to avoid identical clips.
    print(f"[{persona_id}] extracting sample ({sample_sec}s @ 24kHz mono) …")
    _ffmpeg_trim(
        source_path,
        sample,
        start=start_sec + 2.0,
        duration=sample_sec,
    )

    # Write a SOURCE.md note for metadata fill.
    source_md = voice_dir / "SOURCE.md"
    source_md.write_text(
        (
            f"# Voice source for persona '{persona_id}'\n\n"
            f"- Source URL: {url}\n"
            f"- Downloaded: fresh-cut reference + sample via "
            "scripts/persona_generator/source_voice.py\n"
            f"- Processing: ffmpeg -> 24kHz mono 16-bit PCM WAV\n"
            f"- Reference: `reference.wav` — {reference_sec:.1f}s starting at "
            f"{start_sec:.1f}s into the source\n"
            f"- Sample: `sample.wav` — {sample_sec:.1f}s starting at "
            f"{start_sec + 2.0:.1f}s into the source\n\n"
            "Transfer these details into `metadata.yaml` under "
            "`assets.voice_reference` and `assets.voice_sample`.\n"
        ),
        encoding="utf-8",
    )

    # Clean up downloaded source to keep pack size small — the SOURCE.md
    # and metadata.yaml link back to the original URL for regeneration.
    source_path.unlink(missing_ok=True)

    return reference, sample


def _download(url: str, out: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "aether-persona-generator/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp, out.open("wb") as fh:
        shutil.copyfileobj(resp, fh)


def _ffmpeg_trim(source: Path, dest: Path, *, start: float, duration: float) -> None:
    """Trim a section of `source` to 24kHz mono 16-bit PCM WAV at `dest`.

    -ar 24000: 24 kHz (Chatterbox native)
    -ac 1:    mono
    -c:a pcm_s16le: 16-bit signed PCM — the format `wave.open()` parses.
    -y:       overwrite
    -af loudnorm: light loudness normalisation so output level is consistent.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.2f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.2f}",
        "-ar",
        "24000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        "-af",
        "loudnorm=I=-18:TP=-2:LRA=11",
        str(dest),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if completed.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed:\n" + completed.stderr[-800:]
        )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("persona_id")
    parser.add_argument("--url", required=True, help="MP3/WAV source URL")
    parser.add_argument("--start-sec", type=float, default=5.0)
    parser.add_argument("--reference-sec", type=float, default=20.0)
    parser.add_argument("--sample-sec", type=float, default=4.0)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    source(
        args.persona_id,
        args.url,
        start_sec=args.start_sec,
        reference_sec=args.reference_sec,
        sample_sec=args.sample_sec,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
