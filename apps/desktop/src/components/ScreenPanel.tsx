import { useCallback, useEffect, useRef, useState } from "react";

import {
  analyzeFrame,
  getMediaPermissions,
  setMediaPermission,
} from "../lib/api";
import { pushCue, readCueHistory } from "../lib/cueHistory";
import type {
  FrameAnalysisOutcome,
  MediaPermissions,
  TranscriptMessage,
} from "../lib/types";

import { ActiveVisionRoute } from "./ActiveVisionRoute";
import { CueHistoryStrip } from "./CueHistoryStrip";
import { VisionBadge } from "./VisionBadge";

interface Props {
  open: boolean;
  onClose: () => void;
  onFrameAnalyzed: (msg: TranscriptMessage) => void;
}

/**
 * Screen-capture sibling to CameraPanel.
 *
 * Uses `navigator.mediaDevices.getDisplayMedia` (the standard browser
 * screen-capture API) so the OS picker drives source selection — Companion
 * never enumerates open windows itself, which keeps this surface
 * minimal and OS-policy-aligned. Same start/stop/sample-frame model as
 * CameraPanel; same in-app permission gate; same `analyze_frame`
 * pipeline. Only one screenshot at a time — no continuous watching.
 */
export function ScreenPanel({ open, onClose, onFrameAnalyzed }: Props) {
  const [perms, setPerms] = useState<MediaPermissions | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [cueHistory, setCueHistory] = useState<string[]>([]);
  const [routeKey, setRouteKey] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setCueHistory(readCueHistory("screen"));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    getMediaPermissions()
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

  useEffect(() => {
    if (!open && stream) {
      stream.getTracks().forEach((t) => t.stop());
      setStream(null);
    }
  }, [open, stream]);
  useEffect(() => {
    return () => {
      if (stream) stream.getTracks().forEach((t) => t.stop());
    };
  }, [stream]);

  const startCapture = useCallback(async () => {
    setErr(null);
    if (perms?.screen === "deny") {
      setErr("Screen capture is set to Never in Settings. Enable it there first.");
      return;
    }
    if (perms?.screen === "ask") {
      setErr(
        "Screen permission is Ask. Approve it in Settings → Media to continue.",
      );
      return;
    }
    setBusy(true);
    try {
      // `getDisplayMedia` triggers the OS source picker — user picks
      // monitor / window / tab. Audio explicitly off; we only want the
      // visual frame for analysis.
      const s = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false,
      });
      // If the user revokes the OS-level capture (clicks "Stop sharing"
      // in the browser's screen-share toolbar), the track ends and we
      // need to clear local state.
      s.getVideoTracks().forEach((t) => {
        t.addEventListener("ended", () => {
          setStream((curr) => {
            if (curr === s) return null;
            return curr;
          });
        });
      });
      setStream(s);
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        await videoRef.current.play().catch(() => undefined);
      }
    } catch (e) {
      setErr(`Could not capture the screen: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }, [perms]);

  const stopCapture = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      setStream(null);
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  }, [stream]);

  const allowScreen = useCallback(async () => {
    setBusy(true);
    try {
      const p = await setMediaPermission("screen", "allow");
      setPerms(p);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const captureAndAnalyze = useCallback(async () => {
    if (!stream || !videoRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current ?? document.createElement("canvas");
    canvasRef.current = canvas;
    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setErr("2D canvas context is unavailable.");
      return;
    }
    ctx.drawImage(video, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.78);
    setBusy(true);
    setErr(null);
    try {
      const trimmedNote = note.trim();
      const outcome: FrameAnalysisOutcome = await analyzeFrame({
        kind: "screen",
        frame_data_url: dataUrl,
        note: trimmedNote || null,
      });
      if (outcome.message) {
        onFrameAnalyzed(outcome.message);
      }
      if (trimmedNote && outcome.kind === "frame_analyzed") {
        setCueHistory(pushCue("screen", trimmedNote));
      }
      if (
        outcome.kind === "permission_denied" ||
        outcome.kind === "permission_ask"
      ) {
        const p = await getMediaPermissions();
        setPerms(p);
      }
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }, [stream, note, onFrameAnalyzed]);

  if (!open) return null;

  const screenState = perms?.screen ?? "ask";
  const captureOn = !!stream;
  const canStart = screenState === "allow" && !captureOn;
  const canCapture = captureOn && !busy;

  return (
    <div
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-aether-border bg-aether-surface shadow-neuRaised animate-fadeIn"
      role="complementary"
      aria-label="Screen capture"
    >
      <div className="flex items-center justify-between border-b border-aether-border px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Screen
          </div>
          <div className="text-[13px] text-aether-text">
            {captureOn ? "Capture is ON" : "Capture is OFF"}
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

        {screenState === "deny" && (
          <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3 text-aether-muted">
            Screen capture is set to{" "}
            <span className="text-aether-err">Never</span> in Settings.
            Change it under Settings → Media to continue.
          </div>
        )}

        {screenState === "ask" && (
          <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3">
            <div className="text-[12.5px] text-aether-text">
              Screen permission is currently{" "}
              <span className="text-aether-warn">Ask</span>.
            </div>
            <p className="mt-1 text-[11.5px] text-aether-muted">
              Allow screen capture for this session so Companion can sample a
              single screenshot. The OS picker still chooses what's
              shared.
            </p>
            <button
              type="button"
              onClick={allowScreen}
              disabled={busy}
              className="mt-3 rounded-md border border-aether-borderHi bg-aether-elevated px-3 py-1.5 text-[12px] text-aether-text hover:border-aether-accent"
            >
              Allow screen capture
            </button>
          </div>
        )}

        <div className="mt-4 aspect-video w-full overflow-hidden rounded-md border border-aether-border bg-black/40">
          <video
            ref={videoRef}
            playsInline
            muted
            className="h-full w-full object-contain"
          />
        </div>

        <div className="mt-3 flex items-center gap-2">
          <span
            aria-label={captureOn ? "screen capture on" : "screen capture off"}
            className={`inline-block h-2 w-2 rounded-full ${
              captureOn ? "bg-aether-err" : "bg-aether-muted/60"
            }`}
          />
          <span className="text-[11px] text-aether-muted">
            {captureOn
              ? "Live preview — screenshot is local until you analyze it"
              : "No frames captured"}
          </span>
        </div>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={startCapture}
            disabled={!canStart || busy}
            className="flex-1 rounded-md border border-aether-border bg-aether-elevated px-3 py-1.5 text-[12px] text-aether-text hover:border-aether-borderHi disabled:opacity-50"
          >
            Start screen capture
          </button>
          <button
            type="button"
            onClick={stopCapture}
            disabled={!captureOn}
            className="flex-1 rounded-md border border-aether-border bg-transparent px-3 py-1.5 text-[12px] text-aether-muted hover:border-aether-borderHi hover:text-aether-text disabled:opacity-50"
          >
            Stop
          </button>
        </div>

        <div className="mt-5 border-t border-aether-border pt-4">
          <VisionBadge
            refreshKey={routeKey}
            onRouteChanged={() => setRouteKey((k) => k + 1)}
          />
          <label className="mt-3 block text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Optional note
          </label>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What should I help with on this screen?"
            className="mt-1 w-full rounded-md border border-aether-border bg-aether-elevated px-2.5 py-1.5 text-[12px] text-aether-text placeholder:text-aether-dim focus:outline-none focus:ring-1 focus:ring-aether-accent"
          />
          <CueHistoryStrip cues={cueHistory} onPick={(cue) => setNote(cue)} />
          <ActiveVisionRoute refreshKey={routeKey} />
          <button
            type="button"
            onClick={captureAndAnalyze}
            disabled={!canCapture}
            className="mt-3 w-full rounded-md border border-aether-borderHi bg-aether-elevated px-3 py-1.5 text-[12px] text-aether-text hover:border-aether-accent disabled:opacity-50"
          >
            {busy ? "Working…" : "Analyze current screenshot"}
          </button>
          <p className="mt-2 text-[11px] text-aether-dim">
            One screenshot per click. No continuous watching. Same audit
            and memory path as a text turn.
          </p>
        </div>
      </div>
    </div>
  );
}
