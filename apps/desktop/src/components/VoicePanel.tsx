import { useCallback, useEffect, useRef, useState } from "react";

import {
  getMicPermission,
  setMicPermission,
  transcribeUtterance,
} from "../lib/api";
import { pcmToWavDataUrl } from "../lib/wavEncoder";
import type { MicPermission, TranscriptMessage } from "../lib/types";

import { ActiveVoiceRoute } from "./ActiveVoiceRoute";
import { VoiceBadge } from "./VoiceBadge";

interface Props {
  open: boolean;
  onClose: () => void;
  onUtteranceTranscribed: (msg: TranscriptMessage) => void;
}

/** Voice V1 single-utterance target sample rate. whisper.cpp is
 * natively 16 kHz mono; matching here avoids an extra resample. */
const CAPTURE_SAMPLE_RATE = 16000;
const CAPTURE_CHANNELS = 1;

type RecorderState = "idle" | "recording" | "processing";

/**
 * Push-to-talk voice panel (Voice V1 step 5).
 *
 * Responsibilities:
 *   - Check the mic permission posture before touching the
 *     microphone. `deny` short-circuits; `ask` surfaces a one-click
 *     allow flip; `allow` lets us request the device.
 *   - Wrap `navigator.mediaDevices.getUserMedia({ audio })` +
 *     WebAudio in a single-utterance capture: press-and-hold or
 *     toggle Record, stop, serialise as 16 kHz mono WAV, send.
 *   - Default to OFF. The mic is only opened when the user hits
 *     Record; the stream is torn down as soon as capture ends or
 *     the panel closes.
 *   - Hand the transcript envelope to App via
 *     `onUtteranceTranscribed`. No assistant-reply plumbing lives
 *     here — the shell's turn engine is what produces the
 *     transcript message this callback receives.
 *   - No continuous listening. No wake word. No VAD. Single
 *     utterance per explicit user action.
 */
export function VoicePanel({ open, onClose, onUtteranceTranscribed }: Props) {
  const [perms, setPerms] = useState<MicPermission | null>(null);
  const [state, setState] = useState<RecorderState>("idle");
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [routeKey, setRouteKey] = useState(0);

  // Capture primitives — refs so we can tear them down across
  // re-renders without triggering effect churn.
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const buffersRef = useRef<Float32Array[]>([]);
  const recordStartRef = useRef<number>(0);

  // Load mic permission when the panel opens.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    getMicPermission()
      .then((p) => {
        if (!cancelled) setPerms(p);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const teardown = useCallback(() => {
    try {
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current.onaudioprocess = null;
      }
      if (sourceRef.current) sourceRef.current.disconnect();
      if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
        audioCtxRef.current.close().catch(() => undefined);
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    } finally {
      processorRef.current = null;
      sourceRef.current = null;
      audioCtxRef.current = null;
      streamRef.current = null;
    }
  }, []);

  // Tear down any live capture whenever the panel closes.
  useEffect(() => {
    if (!open) teardown();
  }, [open, teardown]);
  useEffect(() => teardown, [teardown]);

  const allowMic = useCallback(async () => {
    try {
      const p = await setMicPermission("allow");
      setPerms(p);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  const startRecording = useCallback(async () => {
    setErr(null);
    setInfo(null);
    if (perms?.state === "deny") {
      setErr(
        "Microphone is set to Never in Settings. Change it under Settings → Microphone to continue.",
      );
      return;
    }
    if (perms?.state === "ask") {
      setErr(
        "Microphone permission is Ask. Approve it before recording — click “Allow microphone” below.",
      );
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: CAPTURE_CHANNELS,
          sampleRate: CAPTURE_SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
        },
        video: false,
      });
      streamRef.current = stream;

      // Prefer the target sample rate but some platforms (Windows
      // WASAPI, macOS Core Audio) only give us 44.1 / 48 kHz. We
      // request 16 kHz on the constraint and let the browser pick
      // its closest legal rate; the WAV encoder then writes the
      // actual context rate so whisper.cpp sees an honest header.
      const AudioCtxCtor =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext })
          .webkitAudioContext;
      const ctx = new AudioCtxCtor({ sampleRate: CAPTURE_SAMPLE_RATE });
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      sourceRef.current = source;
      // ScriptProcessorNode is deprecated but widely supported and
      // synchronous — simpler than AudioWorklet for a single
      // push-to-talk capture. If AudioWorklet becomes necessary a
      // future slice can swap it.
      const processor = ctx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;
      buffersRef.current = [];
      processor.onaudioprocess = (event: AudioProcessingEvent) => {
        const input = event.inputBuffer.getChannelData(0);
        buffersRef.current.push(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(ctx.destination);

      recordStartRef.current = Date.now();
      setState("recording");
    } catch (e) {
      setErr(`Could not start microphone: ${String(e)}`);
      teardown();
    }
  }, [perms, teardown]);

  const stopAndTranscribe = useCallback(async () => {
    if (state !== "recording") return;
    setState("processing");
    const ctx = audioCtxRef.current;
    const buffers = buffersRef.current;
    const durationMs = Math.max(1, Date.now() - recordStartRef.current);
    // Stop the mic immediately so the indicator dies as soon as the
    // user releases; the rest of the work happens off-device.
    teardown();
    buffersRef.current = [];
    if (!ctx || buffers.length === 0) {
      setErr("No audio captured. Try again.");
      setState("idle");
      return;
    }
    const total = buffers.reduce((n, b) => n + b.length, 0);
    const merged = new Float32Array(total);
    let offset = 0;
    for (const b of buffers) {
      merged.set(b, offset);
      offset += b.length;
    }
    const sampleRate = ctx.sampleRate; // honest value written into WAV header
    try {
      const dataUrl = pcmToWavDataUrl(merged, sampleRate, CAPTURE_CHANNELS);
      const outcome = await transcribeUtterance({
        utterance_data_url: dataUrl,
        duration_ms: durationMs,
        cue: null,
        sample_rate: sampleRate,
        channels: CAPTURE_CHANNELS,
        language: null,
      });
      if (outcome.message) {
        onUtteranceTranscribed(outcome.message);
      }
      // Reflect any permission-state hint the backend returned.
      if (
        outcome.kind === "mic_permission_denied" ||
        outcome.kind === "mic_permission_ask"
      ) {
        const p = await getMicPermission();
        setPerms(p);
      }
      if (outcome.kind === "utterance_transcribed") {
        setInfo(`Captured ${(durationMs / 1000).toFixed(1)}s of audio.`);
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setState("idle");
    }
  }, [state, teardown, onUtteranceTranscribed]);

  // Release the mic if the user just closed the panel mid-record.
  useEffect(() => {
    if (!open && state !== "idle") {
      teardown();
      setState("idle");
    }
  }, [open, state, teardown]);

  if (!open) return null;

  const micState = perms?.state ?? "ask";
  const isRecording = state === "recording";
  const isProcessing = state === "processing";

  return (
    <div
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-aether-border bg-aether-surface shadow-neuRaised animate-fadeIn"
      role="complementary"
      aria-label="Voice"
    >
      <div className="flex items-center justify-between border-b border-aether-border px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Voice
          </div>
          <div className="text-[13px] text-aether-text">
            {isRecording
              ? "Recording…"
              : isProcessing
                ? "Transcribing…"
                : "Push-to-talk · single utterance"}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11px] text-aether-muted hover:border-aether-text hover:text-aether-text"
        >
          Close
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 text-[12.5px]">
        {err && (
          <div className="mb-3 rounded-md border border-aether-err/40 bg-aether-err/5 px-3 py-2 text-aether-err">
            {err}
          </div>
        )}
        {info && !err && (
          <div className="mb-3 rounded-md border border-aether-ok/40 bg-aether-ok/5 px-3 py-2 text-aether-ok">
            {info}
          </div>
        )}

        {micState === "deny" && (
          <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3 text-aether-muted">
            Microphone is set to{" "}
            <span className="text-aether-err">Never</span> in Settings.
            Change it under Settings → Microphone to continue.
          </div>
        )}

        {micState === "ask" && (
          <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3">
            <div className="text-[12.5px] text-aether-text">
              Microphone permission is currently{" "}
              <span className="text-aether-warn">Ask</span>.
            </div>
            <p className="mt-1 text-[11.5px] text-aether-muted">
              Allow microphone access for this session so Companion can hear
              a single utterance when you hold Record. You can revert the
              choice at any time in Settings.
            </p>
            <button
              type="button"
              onClick={allowMic}
              className="mt-3 rounded-md border border-aether-borderHi bg-aether-elevated px-3 py-1.5 text-[12px] text-aether-text hover:border-aether-accent"
            >
              Allow microphone
            </button>
          </div>
        )}

        <div className="mt-4 flex items-center gap-2">
          <span
            aria-label={isRecording ? "microphone on" : "microphone off"}
            className={`inline-block h-2 w-2 rounded-full ${
              isRecording
                ? "animate-pulse bg-aether-err"
                : "bg-aether-muted/60"
            }`}
          />
          <span className="text-[11px] text-aether-muted">
            {isRecording
              ? "Live capture — audio bytes are transient"
              : "No audio captured"}
          </span>
        </div>

        <div className="mt-5 border-t border-aether-border pt-4">
          <VoiceBadge
            refreshKey={routeKey}
            onRouteChanged={() => setRouteKey((k) => k + 1)}
          />
          <ActiveVoiceRoute refreshKey={routeKey} />
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onMouseDown={startRecording}
              onMouseUp={stopAndTranscribe}
              onMouseLeave={() => {
                if (isRecording) stopAndTranscribe();
              }}
              onTouchStart={(e) => {
                e.preventDefault();
                startRecording();
              }}
              onTouchEnd={(e) => {
                e.preventDefault();
                stopAndTranscribe();
              }}
              disabled={
                micState === "deny" || isProcessing
              }
              aria-pressed={isRecording}
              className={`flex-1 rounded-md border px-3 py-2 text-[12px] transition-colors disabled:opacity-50 ${
                isRecording
                  ? "border-aether-err bg-aether-err/10 text-aether-err"
                  : "border-aether-borderHi bg-aether-elevated text-aether-text hover:border-aether-accent"
              }`}
            >
              {isRecording
                ? "Release to transcribe"
                : isProcessing
                  ? "Transcribing…"
                  : "Hold to record"}
            </button>
          </div>
          <p className="mt-2 text-[11px] text-aether-dim">
            Press and hold to capture a single utterance. Audio is
            encoded locally, sent once, then discarded — only the
            transcript is stored.
          </p>
        </div>
      </div>
    </div>
  );
}
