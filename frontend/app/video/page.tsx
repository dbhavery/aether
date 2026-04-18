"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { getWsClient } from "@/lib/ws";
import { ExtendedEventType } from "@/lib/types";
import { useSessionStore } from "@/lib/stores/session";
import { useWizardStore } from "@/lib/stores/wizard";
import { findPersona } from "@/lib/personas";

const MJPEG_URL = "http://localhost:8770/stream";

type StreamState = "unknown" | "streaming" | "error";

export default function VideoPage() {
  const wsStatus = useSessionStore((s) => s.wsStatus);
  const activeName = useSessionStore((s) => s.activeDisplayName);
  const activeId = useSessionStore((s) => s.activePersonaId);
  const fallbackId = useWizardStore((s) => s.selectedAvatarId);
  const fallbackName = useWizardStore((s) => s.displayName);

  const persona = findPersona(activeId ?? fallbackId ?? "");
  const displayName = activeName ?? fallbackName ?? persona?.displayName ?? "Aether";

  const [streamState, setStreamState] = useState<StreamState>("unknown");
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  return (
    <div className="relative h-full w-full bg-black">
      <AvatarStream state={streamState} setState={setStreamState} />

      <header className="absolute top-4 left-0 right-0 flex justify-center pointer-events-none">
        <div className="pointer-events-auto px-3 py-1.5 rounded-full border border-border-subtle bg-bg-0/70 backdrop-blur text-[12px] text-fg-secondary">
          {displayName}
        </div>
      </header>

      <PushToTalk disabled={wsStatus !== "connected"} />

      <button
        type="button"
        onClick={() => setTranscriptOpen((v) => !v)}
        className="absolute top-4 right-4 text-[12px] text-fg-muted hover:text-fg-primary bg-bg-1/70 border border-border-subtle rounded-md px-3 py-1.5 backdrop-blur"
      >
        {transcriptOpen ? "Hide transcript" : "Show transcript"}
      </button>

      {transcriptOpen && <TranscriptDrawer onClose={() => setTranscriptOpen(false)} />}
    </div>
  );
}

function AvatarStream({
  state,
  setState,
}: {
  state: StreamState;
  setState(state: StreamState): void;
}) {
  if (state === "error") {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-6 gap-3">
        <p className="text-[15px] text-fg-secondary">Avatar subsystem isn't ready yet.</p>
        <p className="text-[12px] text-fg-muted max-w-md">
          This usually means the backend is still booting, or you finished onboarding without
          enabling the avatar. Switch to chat for now.
        </p>
      </div>
    );
  }

  // Using a plain <img> is the MJPEG idiom — Chrome streams the multipart
  // response into continuous frames. `unoptimized` + static export means
  // we never hand this off to next/image.
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={MJPEG_URL}
      alt="Live avatar stream"
      draggable={false}
      onLoad={() => setState("streaming")}
      onError={() => setState("error")}
      className="absolute inset-0 w-full h-full object-cover select-none"
    />
  );
}

function PushToTalk({ disabled }: { disabled: boolean }) {
  const [active, setActive] = useState(false);
  const requestIdRef = useRef<string>("");

  const startTalk = (): void => {
    if (disabled || active) return;
    setActive(true);
    const requestId = `ptt-${Date.now().toString(36)}`;
    requestIdRef.current = requestId;
    getWsClient().send(ExtendedEventType.USER_SPEECH_START, { request_id: requestId });
  };

  const stopTalk = (): void => {
    if (!active) return;
    setActive(false);
    getWsClient().send(ExtendedEventType.USER_SPEECH_END, { request_id: requestIdRef.current });
  };

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent): void => {
      if (e.code === "Space" && !e.repeat && document.activeElement?.tagName !== "TEXTAREA") {
        e.preventDefault();
        startTalk();
      }
    };
    const onKeyUp = (e: KeyboardEvent): void => {
      if (e.code === "Space") {
        e.preventDefault();
        stopTalk();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
    // `startTalk`/`stopTalk` are stable enough here — they read from refs/state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled]);

  return (
    <div className="absolute bottom-6 left-0 right-0 flex justify-center">
      <button
        type="button"
        disabled={disabled}
        onMouseDown={startTalk}
        onMouseUp={stopTalk}
        onMouseLeave={stopTalk}
        onTouchStart={(e) => {
          e.preventDefault();
          startTalk();
        }}
        onTouchEnd={(e) => {
          e.preventDefault();
          stopTalk();
        }}
        className={[
          "rounded-full px-6 py-4 text-[13px] font-medium",
          "border transition-colors duration-150",
          active
            ? "bg-accent text-black border-accent shadow-[var(--shadow-float)]"
            : "bg-bg-1/80 text-fg-primary border-border-default hover:bg-bg-2 backdrop-blur",
          disabled ? "opacity-50 cursor-not-allowed" : "",
        ].join(" ")}
        aria-pressed={active}
        aria-label="Hold to talk"
      >
        {active ? "● Listening" : "Hold space to talk"}
      </button>
    </div>
  );
}

function TranscriptDrawer({ onClose }: { onClose(): void }) {
  return (
    <aside
      className="absolute top-16 right-4 bottom-20 w-[min(360px,40vw)] overflow-auto rounded-[var(--radius-lg)] bg-bg-1/90 backdrop-blur border border-border-default p-4 text-[13px]"
      aria-label="Live transcript"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] uppercase tracking-[0.16em] text-fg-muted">Transcript</div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Close
        </Button>
      </div>
      <p className="text-fg-muted text-[12px]">
        Speech recognized via the backend's voice pipeline will appear here as it arrives.
      </p>
    </aside>
  );
}
