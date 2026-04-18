"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { SelectableCard } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { getWsClient } from "@/lib/ws";
import { ExtendedEventType, WizardStepId, type VoiceMode } from "@/lib/types";
import { useWizardStore } from "@/lib/stores/wizard";
import { WizardStepShell } from "./WizardStepShell";

export function StepVoice() {
  const router = useRouter();
  const storedMode = useWizardStore((s) => s.voiceMode);
  const submitStep = useWizardStore((s) => s.submitStep);

  const [selected, setSelected] = useState<VoiceMode>(storedMode ?? "local");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [elevenKey, setElevenKey] = useState<string>("");
  const [elevenTestState, setElevenTestState] = useState<"idle" | "testing" | "ok" | "error">(
    "idle",
  );
  const [elevenTestMessage, setElevenTestMessage] = useState<string>("");

  const [hwState, setHwState] = useState<"probing" | "ready" | "warn" | "missing">("probing");
  const [hwDetail, setHwDetail] = useState<string>("");
  const hwReqRef = useRef<string>("");

  useEffect(() => {
    if (selected !== "local") return;
    const ws = getWsClient();
    const requestId = `vhp-${Date.now().toString(36)}`;
    hwReqRef.current = requestId;
    setHwState("probing");
    const unsub = ws.subscribe(ExtendedEventType.VOICE_HARDWARE_PROBE_RESULT, (event) => {
      const data = event.data as {
        request_id?: string;
        gpu?: string | null;
        vram_gb?: number;
        sufficient?: boolean;
      };
      if (data.request_id !== requestId) return;
      if (data.sufficient) {
        setHwState("ready");
        setHwDetail(
          data.gpu && typeof data.vram_gb === "number"
            ? `${data.gpu}, ${data.vram_gb.toFixed(0)} GB VRAM. Local voice will run smoothly.`
            : "Hardware is sufficient for local voice.",
        );
      } else if (data.gpu) {
        setHwState("warn");
        setHwDetail(
          `${data.gpu}${
            typeof data.vram_gb === "number" ? `, ${data.vram_gb.toFixed(0)} GB VRAM` : ""
          }. Local voice may be slow. Consider cloud voice or skip.`,
        );
      } else {
        setHwState("missing");
        setHwDetail("No GPU detected. Local voice will be slow. Consider cloud voice or skip.");
      }
    });
    ws.send(ExtendedEventType.VOICE_HARDWARE_PROBE_REQUEST, { request_id: requestId });
    const timer = setTimeout(() => {
      if (hwReqRef.current === requestId) {
        setHwState((prev) => (prev === "probing" ? "missing" : prev));
        setHwDetail((d) => d || "Backend did not respond.");
      }
    }, 2_500);
    return () => {
      clearTimeout(timer);
      unsub();
    };
  }, [selected]);

  const handleTestElevenLabs = (): void => {
    if (!elevenKey.trim()) {
      setElevenTestState("error");
      setElevenTestMessage("Enter your ElevenLabs key first.");
      return;
    }
    setElevenTestState("testing");
    setElevenTestMessage("");
    const ws = getWsClient();
    const requestId = `el-keytest-${Date.now().toString(36)}`;
    const unsub = ws.subscribe(ExtendedEventType.LLM_KEY_TEST_RESULT, (event) => {
      const data = event.data as {
        request_id?: string;
        success?: boolean;
        message?: string;
      };
      if (data.request_id !== requestId) return;
      unsub();
      if (data.success) {
        setElevenTestState("ok");
        setElevenTestMessage(data.message ?? "ElevenLabs reachable.");
      } else {
        setElevenTestState("error");
        setElevenTestMessage(data.message ?? "Key rejected.");
      }
    });
    ws.send(ExtendedEventType.LLM_KEY_TEST_REQUEST, {
      request_id: requestId,
      provider: "elevenlabs",
      api_key: elevenKey,
    });
    setTimeout(() => {
      setElevenTestState((prev) => (prev === "testing" ? "error" : prev));
      setElevenTestMessage((prev) => (prev ? prev : "Backend did not respond."));
    }, 15_000);
  };

  const handleContinue = async (): Promise<void> => {
    setError(null);
    if (selected === "local" && hwState === "missing") {
      setError("No local voice hardware. Switch to cloud voice or skip.");
      return;
    }
    if (selected === "elevenlabs" && elevenTestState !== "ok") {
      setError("Test your ElevenLabs key before continuing.");
      return;
    }

    setBusy(true);
    try {
      const result = await submitStep(WizardStepId.VOICE, {
        voice_mode: selected,
        voice_settings: selected === "elevenlabs" ? { elevenlabs_configured: true } : {},
      });
      if (result.success) router.push("/onboarding/7-terms/");
      else if (result.error) setError(result.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <WizardStepShell
      step={WizardStepId.VOICE}
      title="Give them a voice."
      subtitle="Expressive speech is optional. You can add or remove it later."
      footer={
        <>
          <Button variant="ghost" onClick={() => router.push("/onboarding/5-llm/")}>
            ← Back
          </Button>
          <Button size="lg" onClick={handleContinue} isLoading={busy}>
            Continue
          </Button>
        </>
      }
    >
      {error && (
        <div
          role="alert"
          className="mb-4 px-4 py-2 rounded-md border border-error/50 bg-error/10 text-error text-[12px]"
        >
          {error}
        </div>
      )}
      <div role="radiogroup" aria-label="Voice mode" className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <SelectableCard
          selected={selected === "local"}
          onClick={() => setSelected("local")}
          className="p-5"
        >
          <div className="text-[10px] uppercase tracking-[0.18em] text-accent/90">Recommended</div>
          <div className="mt-1 text-[15px] font-medium text-fg-primary">Local voice</div>
          <div className="text-[12px] text-fg-muted mt-1">Runs on your GPU. Private, no cost.</div>
          <div className="mt-4 text-[12px] space-y-1">
            {hwState === "probing" && <span className="text-fg-muted">Detecting hardware…</span>}
            {hwState === "ready" && <span className="text-ok">{hwDetail}</span>}
            {hwState === "warn" && <span className="text-warn">{hwDetail}</span>}
            {hwState === "missing" && <span className="text-error">{hwDetail}</span>}
          </div>
          <div className="mt-2 text-[11px] text-fg-muted">
            Downloads required: faster-whisper base (~200&nbsp;MB), Chatterbox Turbo (~800&nbsp;MB).
          </div>
        </SelectableCard>

        <SelectableCard
          selected={selected === "elevenlabs"}
          onClick={() => setSelected("elevenlabs")}
          className="p-5"
        >
          <div className="text-[10px] uppercase tracking-[0.18em] text-accent/90">Cloud</div>
          <div className="mt-1 text-[15px] font-medium text-fg-primary">ElevenLabs</div>
          <div className="text-[12px] text-fg-muted mt-1">Fastest, highest quality. Costs apply.</div>
          {selected === "elevenlabs" && (
            <div className="mt-4 space-y-3" onClick={(e) => e.stopPropagation()}>
              <Input
                type="password"
                placeholder="ElevenLabs API key"
                value={elevenKey}
                onChange={(e) => {
                  setElevenKey(e.target.value);
                  setElevenTestState("idle");
                }}
                autoComplete="off"
                spellCheck={false}
              />
              <div className="flex items-center gap-3">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleTestElevenLabs}
                  isLoading={elevenTestState === "testing"}
                >
                  Test key
                </Button>
                {elevenTestState !== "idle" && (
                  <span
                    className={`text-[11px] ${
                      elevenTestState === "ok"
                        ? "text-ok"
                        : elevenTestState === "error"
                          ? "text-error"
                          : "text-fg-muted"
                    }`}
                  >
                    {elevenTestMessage || (elevenTestState === "testing" ? "Testing…" : "")}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-fg-muted">
                ElevenLabs charges per character. You'll see usage in Sandbox → Voice.
              </p>
            </div>
          )}
        </SelectableCard>

        <SelectableCard
          selected={selected === "off"}
          onClick={() => setSelected("off")}
          className="p-5"
        >
          <div className="text-[10px] uppercase tracking-[0.18em] text-fg-muted">Skip</div>
          <div className="mt-1 text-[15px] font-medium text-fg-primary">Text only for now</div>
          <div className="text-[12px] text-fg-muted mt-1">
            Enable voice any time from Sandbox → Voice.
          </div>
        </SelectableCard>
      </div>
    </WizardStepShell>
  );
}
