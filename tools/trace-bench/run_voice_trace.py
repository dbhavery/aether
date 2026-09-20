"""Drive one real turn through Aether's voice path and record its timings.

This is the bench that produced the only latency figures anyone should quote
about this repo. It runs the PRODUCTION code path: the real ``VoicePipeline``,
the real ``EventBus``, the real brain handler, the real ``litellm`` client, the
real STT and TTS engines, and the real ``src.core.trace`` instrument. Nothing
about the timing is simulated.

The one thing it replaces is the microphone: instead of waiting for a spacebar
press it loads a WAV file into the capture buffer and fires the same
``USER_SPEECH_END`` handler that push-to-talk fires. Everything downstream of
that is untouched production code.

    # Full voice path: real faster-whisper STT, real Ollama LLM, real Chatterbox TTS
    py -V:3.13 tools/trace-bench/run_voice_trace.py --wav personas/aurora/voice/sample.wav

    # Text path only, no audio engines involved
    py -V:3.13 tools/trace-bench/run_voice_trace.py --text "what is the low air warning pressure"

    # Skip TTS to isolate STT + LLM
    py -V:3.13 tools/trace-bench/run_voice_trace.py --wav <path> --no-tts

Always prints which components were real and which were skipped, because a
latency number without its path and its hardware is not a measurement.

Use a local model. This bench is for measuring, not for spending money on a
metered provider.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import platform
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


_CONFIG_TEMPLATE = """\
aether:
  version: 1
  user_installation_id: "00000000-0000-4000-8000-00000000bench"
  telemetry:
    enabled: true
    crash_reports: false
    usage_counters: true

onboarding:
  complete: true
  current_step: "done"

persona:
  active: "{persona}"
  display_name: "Bench"

llm:
  provider: "ollama"
  tier_map:
    fast: "{model}"
    main: "{model}"
    heavy: "{model}"

voice:
  device: "default"
  stt_mode: "whisper"
  tts_mode: "chatterbox"
"""


def _write_bench_config(config_dir: Path, *, model: str, persona: str) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "config.yaml"
    path.write_text(_CONFIG_TEMPLATE.format(model=model, persona=persona), encoding="utf-8")
    return path


def _describe_hardware() -> list[str]:
    lines = [
        f"host      : {platform.node()}",
        f"os        : {platform.system()} {platform.release()} ({platform.machine()})",
        f"python    : {platform.python_version()} at {sys.executable}",
    ]
    try:
        import torch

        if torch.cuda.is_available():
            lines.append(f"gpu       : {torch.cuda.get_device_name(0)} (torch {torch.__version__})")
        else:
            lines.append(f"gpu       : none visible to torch {torch.__version__}")
    except Exception as exc:
        lines.append(f"gpu       : torch unavailable ({exc!r})")
    return lines


async def _run(args: argparse.Namespace) -> int:
    import numpy as np

    # Point the data dir somewhere explicit BEFORE importing anything that
    # resolves paths, so a bench run never writes into the installed app's data.
    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AETHER_DATA_DIR"] = str(data_dir)

    import src.shared.config as config_mod

    config_path = _write_bench_config(data_dir / "config", model=args.model, persona=args.persona)
    config_mod.get_config_path = lambda: config_path  # type: ignore[assignment]
    config_mod._config_cache = None
    config_mod._raw_cache = None
    config_mod._raw_cache_path = None
    config_mod._load_yaml_dict.cache_clear()

    import src.brain.handler as brain_handler
    import src.voice.pipeline as pipeline_mod
    import src.voice.tts_handler as tts_mod
    from src.core import trace
    from src.core.events import event_bus
    from src.shared.types import AetherEvent, EventType

    real = []
    skipped = []

    # --- memory ------------------------------------------------------------
    if args.no_memory:
        async def _skip_persist(*_a, **_kw):
            return None

        async def _no_history(_n):
            return []

        async def _no_rag(_q):
            return []

        brain_handler._persist_turn = _skip_persist  # type: ignore[assignment]
        brain_handler._get_recent_history = _no_history  # type: ignore[assignment]
        brain_handler._get_rag_context = _no_rag  # type: ignore[assignment]
        skipped.append("memory (chroma store, history, RAG) bypassed by --no-memory")
    else:
        real.append("memory: real chroma store + Ollama embeddings")

    # --- LLM ---------------------------------------------------------------
    real.append(f"LLM: real litellm -> {args.model}")

    # --- input -------------------------------------------------------------
    event_bus.subscribe(EventType.USER_MESSAGE, brain_handler.on_user_message)
    if args.no_tts:
        skipped.append("TTS and playback skipped by --no-tts (no tts_synth/first_audio stages)")
    else:
        event_bus.subscribe(EventType.RESPONSE_TEXT_READY, tts_mod.on_response_text_ready)
        real.append("TTS: real Chatterbox synth")
        if args.mute:
            async def _silent(_audio, _rate):
                return None

            tts_mod.play_audio = _silent  # type: ignore[assignment]
            skipped.append("speaker playback silenced by --mute")
        else:
            real.append("playback: real system speakers")

    print("=" * 74)
    print("Aether voice-path latency bench")
    print("=" * 74)
    for line in _describe_hardware():
        print(line)
    print(f"data dir  : {data_dir.as_posix()}")
    print()

    try:
        if args.text is not None:
            real.append("STT: skipped, text supplied directly")
            print(f"input     : text {args.text!r}")
            print()
            trace_turn = trace.start_turn("text", prompt_chars=len(args.text))
            try:
                await event_bus.publish(
                    AetherEvent(
                        type=EventType.USER_MESSAGE,
                        data={"text": args.text, "mode": "voice" if not args.no_tts else "text"},
                        source_module="bench",
                    )
                )
            finally:
                await trace_turn.finish()
        else:
            import soundfile as sf

            wav_path = Path(args.wav).resolve()
            if not wav_path.exists():
                print(f"error: no such wav {wav_path.as_posix()}")
                return 2
            audio, sample_rate = sf.read(str(wav_path), dtype="float32", always_2d=False)
            if getattr(audio, "ndim", 1) > 1:
                audio = audio[:, 0]
            source_rate = sample_rate
            if sample_rate != 16000:
                # The live pipeline opens PortAudio at 16 kHz mono, so a file at
                # any other rate has to be brought to the rate a microphone
                # would have produced. This happens before the turn clock
                # starts, so it cannot inflate any measurement.
                try:
                    from scipy.signal import resample_poly
                except ImportError:
                    print(f"error: {wav_path.name} is {sample_rate} Hz; the pipeline captures 16 kHz mono.")
                    print("       install scipy, or resample first: ffmpeg -i in.wav -ar 16000 -ac 1 out.wav")
                    return 2
                from math import gcd

                divisor = gcd(16000, sample_rate)
                audio = resample_poly(audio, 16000 // divisor, sample_rate // divisor).astype("float32")
                sample_rate = 16000

            real.append("STT: real faster-whisper")
            rate_note = f"{source_rate} Hz" if source_rate == 16000 else f"{source_rate} Hz resampled to 16000 Hz"
            print(f"input     : {wav_path.as_posix()} ({audio.shape[0] / sample_rate:.2f}s, {rate_note})")
            print()

            # Exactly what push-to-talk does, minus PortAudio.
            # Repeat in ONE process so the first turn shows cold model load and
            # the later ones show steady state. Whisper, Chatterbox and Ollama
            # all cache their weights per process, so a second process would
            # measure a cold start again and never reveal the warm figure.
            for turn_index in range(args.turns):
                label = "cold (models loading)" if turn_index == 0 else "warm"
                print(f"--- turn {turn_index + 1} of {args.turns}: {label} ---")
                pipeline = pipeline_mod.VoicePipeline()
                pipeline._listening = True
                pipeline._buffer = [np.asarray(audio, dtype=np.float32)]
                pipeline._buffer_samples = int(audio.shape[0])
                await pipeline._on_speech_end(
                    AetherEvent(type=EventType.USER_SPEECH_END, data={}, source_module="bench")
                )
    finally:
        with contextlib.suppress(Exception):
            event_bus.unsubscribe(EventType.USER_MESSAGE, brain_handler.on_user_message)
        with contextlib.suppress(Exception):
            event_bus.unsubscribe(EventType.RESPONSE_TEXT_READY, tts_mod.on_response_text_ready)

    print()
    print("-" * 74)
    print("what was real in this run")
    for line in real:
        print(f"  + {line}")
    for line in skipped:
        print(f"  - {line}")
    print("-" * 74)
    print()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report import print_turn

    records = await trace.read_traces(limit=args.turns)
    if not records:
        print("No trace was recorded. Check that the bench config granted usage_counters.")
        return 1
    for index, record in enumerate(records):
        if len(records) > 1:
            print(f"=== turn {index + 1} of {len(records)}: "
                  f"{'cold, models loading' if index == 0 else 'warm'} ===")
        print_turn(record)
    print(f"trace log : {trace.traces_path().as_posix()}")
    return 0


def main() -> int:
    default_data = Path(tempfile.gettempdir()) / "aether-trace-bench"
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--wav", help="16 kHz mono WAV to feed the capture buffer (real STT)")
    src.add_argument("--text", help="skip STT and submit this text instead")
    parser.add_argument("--model", default="ollama/qwen3.5:4b", help="litellm model id; keep it local")
    parser.add_argument("--persona", default="aurora", help="persona whose reference.wav clones the voice")
    parser.add_argument("--data-dir", default=str(default_data), help="where to write traces.jsonl and usage.jsonl")
    parser.add_argument(
        "--turns",
        type=int,
        default=1,
        help="repeat the same turn N times in one process; turn 1 is cold, the rest are warm",
    )
    parser.add_argument("--no-tts", action="store_true", help="skip synthesis and playback")
    parser.add_argument("--no-memory", action="store_true", help="skip chroma history and RAG")
    parser.add_argument("--mute", action="store_true", help="synthesize but do not play through speakers")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
