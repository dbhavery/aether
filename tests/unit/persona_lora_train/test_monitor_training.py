"""Tests for monitor_training — pure CPU/disk poll-loop semantics."""

from __future__ import annotations

import io
import time

import monitor_training  # type: ignore[import-not-found]


def test_module_surface():
    assert hasattr(monitor_training, "poll_once")
    assert hasattr(monitor_training, "run")
    assert hasattr(monitor_training, "main")


def test_scan_checkpoints_empty(tmp_path):
    assert monitor_training._scan_checkpoints(tmp_path) == []


def test_scan_checkpoints_recognises_diffusers_layout(tmp_path):
    (tmp_path / "checkpoint-50").mkdir()
    (tmp_path / "checkpoint-500").mkdir()
    (tmp_path / "checkpoint-1500").mkdir()
    (tmp_path / "logs").mkdir()  # non-checkpoint dir
    (tmp_path / "checkpoint-bad").mkdir()  # malformed name → skipped
    (tmp_path / "stray.txt").write_text("x")  # file, not dir
    assert monitor_training._scan_checkpoints(tmp_path) == [50, 500, 1500]


def test_detect_final_adapter_canonical(tmp_path):
    assert monitor_training._detect_final_adapter(tmp_path) is None
    (tmp_path / "pytorch_lora_weights.safetensors").write_bytes(b"\x00")
    detected = monitor_training._detect_final_adapter(tmp_path)
    assert detected is not None
    assert detected.name == "pytorch_lora_weights.safetensors"


def test_detect_final_adapter_alt_basename(tmp_path):
    (tmp_path / "diffusion_pytorch_model.safetensors").write_bytes(b"\x00")
    detected = monitor_training._detect_final_adapter(tmp_path)
    assert detected is not None


def test_poll_once_missing_output_dir(tmp_path):
    state = monitor_training.MonitorState()
    event, _ = monitor_training.poll_once(tmp_path / "ghost", state)
    assert event == "missing-output-dir"


def test_poll_once_final_adapter_short_circuits(tmp_path):
    (tmp_path / "pytorch_lora_weights.safetensors").write_bytes(b"\x00")
    state = monitor_training.MonitorState()
    event, new_state = monitor_training.poll_once(tmp_path, state)
    assert event == "final-adapter"
    assert new_state.final_adapter_seen is True


def test_poll_once_no_checkpoint_yet_initialises_progress_time(tmp_path):
    state = monitor_training.MonitorState()
    event, new_state = monitor_training.poll_once(tmp_path, state)
    assert event == "no-checkpoint-yet"
    assert new_state.last_progress_time > 0


def test_poll_once_progress_advances_step(tmp_path):
    (tmp_path / "checkpoint-50").mkdir()
    state = monitor_training.MonitorState(last_progress_time=time.time() - 10)
    event, new_state = monitor_training.poll_once(tmp_path, state)
    assert event == "checkpoint-progress"
    assert new_state.last_checkpoint_step == 50

    # Add another checkpoint — should advance again.
    (tmp_path / "checkpoint-500").mkdir()
    event2, newer_state = monitor_training.poll_once(tmp_path, new_state)
    assert event2 == "checkpoint-progress"
    assert newer_state.last_checkpoint_step == 500


def test_poll_once_no_advance_returns_stall(tmp_path):
    (tmp_path / "checkpoint-100").mkdir()
    state = monitor_training.MonitorState(last_checkpoint_step=100)
    event, _ = monitor_training.poll_once(tmp_path, state)
    assert event == "stall"


def test_run_returns_zero_on_final_adapter(tmp_path):
    (tmp_path / "pytorch_lora_weights.safetensors").write_bytes(b"\x00")
    buf = io.StringIO()
    rc = monitor_training.run(
        tmp_path,
        poll_seconds=0,
        stall_minutes=999,
        out_stream=buf,
    )
    assert rc == 0
    assert "final adapter detected" in buf.getvalue()


def test_run_returns_three_when_dir_disappears(tmp_path):
    """Output dir that never exists triggers a missing-dir exit."""
    buf = io.StringIO()
    rc = monitor_training.run(
        tmp_path / "ghost",
        poll_seconds=0,
        stall_minutes=999,
        out_stream=buf,
    )
    assert rc == 3
    assert "disappeared" in buf.getvalue()


def test_run_terminates_when_final_adapter_appears_after_progress(tmp_path):
    """Smoke: progress poll sees a checkpoint, then final-adapter, exits clean."""
    (tmp_path / "checkpoint-100").mkdir()
    (tmp_path / "pytorch_lora_weights.safetensors").write_bytes(b"\x00")
    buf = io.StringIO()
    rc = monitor_training.run(
        tmp_path,
        poll_seconds=0,
        stall_minutes=999,
        out_stream=buf,
    )
    assert rc == 0


def test_main_cli_smoke(tmp_path):
    """`main` parses args, dispatches to run(), returns exit code."""
    (tmp_path / "pytorch_lora_weights.safetensors").write_bytes(b"\x00")
    rc = monitor_training.main([
        "--output-dir", str(tmp_path),
        "--poll-seconds", "0",
        "--stall-minutes", "999",
    ])
    assert rc == 0
