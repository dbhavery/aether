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
 * Camera abstraction + panel (P2 + P3 UI slice).
 *
 * Responsibilities:
 *   - Check the local media-permission posture before touching the
 *     camera. If `deny` we never call `getUserMedia`; if `ask` we
 *     surface a one-click inline flip to `allow` so the user is in
 *     control. `allow` lets us request the device.
 *   - Wrap the browser MediaDevices API with a small API — start,
 *     stop, sample-frame — so the rest of the app can treat camera
 *     access as a high-level capability.
 *   - Default to OFF. The camera is only acquired when the user hits
 *     "Start camera" on this panel; it is released when they close
 *     the panel or press "Stop camera".
 *   - Expose a single-frame capture button that serialises the latest
 *     video frame to a data URL and hands it to `analyze_frame` via
 *     the API wrapper. The resulting transcript line is forwarded to
 *     the App so it lands in the main conversation view.
 */
export function CameraPanel({ open, onClose, onFrameAnalyzed }: Props) {
  const [perms, setPerms] = useState<MediaPermissions | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [cueHistory, setCueHistory] = useState<string[]>([]);
  const [routeKey, setRouteKey] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Hydrate the recent-cue list when the panel opens.
  useEffect(() => {
    if (!open) return;
    setCueHistory(readCueHistory("camera"));
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

  // Stop the stream whenever we close the panel or unmount.
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

  const startCamera = useCallback(async () => {
    setErr(null);
    if (perms?.camera === "deny") {
      setErr("Camera is set to Never in Settings. Enable it there first.");
      return;
    }
    if (perms?.camera === "ask") {
      setErr(
        "Camera permission is Ask. Approve it in Settings → Media to continue.",
      );
      return;
    }
    setBusy(true);
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });
      setStream(s);
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        await videoRef.current.play().catch(() => undefined);
      }
    } catch (e) {
      setErr(`Could not access the camera: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  }, [perms]);

  const stopCamera = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      setStream(null);
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  }, [stream]);

  const allowCamera = useCallback(async () => {
    setBusy(true);
    try {
      const p = await setMediaPermission("camera", "allow");
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
    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setErr("2D canvas context is unavailable.");
      return;
    }
    ctx.drawImage(video, 0, 0, width, height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.82);
    setBusy(true);
    setErr(null);
    try {
      const trimmedNote = note.trim();
      const outcome: FrameAnalysisOutcome = await analyzeFrame({
        kind: "camera",
        frame_data_url: dataUrl,
        note: trimmedNote || null,
      });
      if (outcome.message) {
        onFrameAnalyzed(outcome.message);
      }
      // Save the cue only when the call actually went through to a
      // model (not on permission refusals) — we want history to show
      // prompts the user has actually run, not stub strings.
      if (trimmedNote && outcome.kind === "frame_analyzed") {
        setCueHistory(pushCue("camera", trimmedNote));
      }
      // If the backend returned a permission refusal, refresh the
      // local posture so the UI reflects the current state.
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

  const cameraState = perms?.camera ?? "ask";
  const cameraIsOn = !!stream;
  const canStart = cameraState === "allow" && !cameraIsOn;
  const canCapture = cameraIsOn && !busy;

  return (
    <div
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-aether-border bg-aether-surface shadow-neuRaised animate-fadeIn"
      role="complementary"
      aria-label="Camera"
    >
      <div className="flex items-center justify-between border-b border-aether-border px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Camera
          </div>
          <div className="text-[13px] text-aether-text">
            {cameraIsOn ? "Capture is ON" : "Capture is OFF"}
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

        {cameraState === "deny" && (
          <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3 text-aether-muted">
            Camera is set to <span className="text-aether-err">Never</span> in
            Settings. Change it under Settings → Media to continue.
          </div>
        )}

        {cameraState === "ask" && (
          <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3">
            <div className="text-[12.5px] text-aether-text">
              Camera permission is currently{" "}
              <span className="text-aether-warn">Ask</span>.
            </div>
            <p className="mt-1 text-[11.5px] text-aether-muted">
              Allow camera access for this session so Companion can sample a
              frame. You can revert the choice at any time in Settings.
            </p>
            <button
              type="button"
              onClick={allowCamera}
              disabled={busy}
              className="mt-3 rounded-md border border-aether-borderHi bg-aether-elevated px-3 py-1.5 text-[12px] text-aether-text hover:border-aether-accent"
            >
              Allow camera
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
            aria-label={cameraIsOn ? "camera on" : "camera off"}
            className={`inline-block h-2 w-2 rounded-full ${
              cameraIsOn ? "bg-aether-err" : "bg-aether-muted/60"
            }`}
          />
          <span className="text-[11px] text-aether-muted">
            {cameraIsOn ? "Live preview — frames are local only" : "No frames captured"}
          </span>
        </div>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={startCamera}
            disabled={!canStart || busy}
            className="flex-1 rounded-md border border-aether-border bg-aether-elevated px-3 py-1.5 text-[12px] text-aether-text hover:border-aether-borderHi disabled:opacity-50"
          >
            Start camera
          </button>
          <button
            type="button"
            onClick={stopCamera}
            disabled={!cameraIsOn}
            className="flex-1 rounded-md border border-aether-border bg-transparent px-3 py-1.5 text-[12px] text-aether-muted hover:border-aether-borderHi hover:text-aether-text disabled:opacity-50"
          >
            Stop camera
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
            placeholder="What should I look at? (e.g. 'is the kettle on?')"
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
            {busy ? "Working…" : "Analyze current frame"}
          </button>
          <p className="mt-2 text-[11px] text-aether-dim">
            Frames are captured locally and handed to the active vision
            route shown above. Image bytes stay transient — only the cue
            and the model's reply are recorded.
          </p>
        </div>
      </div>
    </div>
  );
}
