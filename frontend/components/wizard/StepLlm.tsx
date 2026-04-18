"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { SelectableCard } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import {
  BYOK_PROVIDERS,
  ExtendedEventType,
  LlmProvider,
  type LlmTierMap,
  WizardStepId,
} from "@/lib/types";
import { useWizardStore } from "@/lib/stores/wizard";
import { getWsClient } from "@/lib/ws";
import { WizardStepShell } from "./WizardStepShell";

type CardId = "local" | "byok" | "guest";

interface TierMapByProvider {
  readonly [key: string]: LlmTierMap;
}

/**
 * Default tier mappings by provider. These match the example in
 * ARCHITECTURE-V2.md §6 and docs/LLM-PROVIDERS.md — the backend is free to
 * override on validation, and we'll hydrate from its response.
 */
const DEFAULT_TIERS: TierMapByProvider = {
  [LlmProvider.ANTHROPIC]: {
    fast: "claude-haiku-4-5",
    main: "claude-sonnet-4-6",
    heavy: "claude-opus-4-7",
  },
  [LlmProvider.OPENAI]: {
    fast: "gpt-4.1-mini",
    main: "gpt-5",
    heavy: "gpt-5-pro",
  },
  [LlmProvider.GOOGLE]: {
    fast: "gemini-2.5-flash",
    main: "gemini-2.5-pro",
    heavy: "gemini-2.5-pro",
  },
  [LlmProvider.GROQ]: {
    fast: "llama-3.3-70b-versatile",
    main: "llama-3.3-70b-versatile",
    heavy: "llama-3.3-70b-versatile",
  },
  [LlmProvider.OPENROUTER]: {
    fast: "openrouter/auto",
    main: "openrouter/auto",
    heavy: "openrouter/auto",
  },
  [LlmProvider.OLLAMA]: {
    fast: "ollama/qwen2.5:7b",
    main: "ollama/qwen2.5:7b",
    heavy: "ollama/qwen2.5:7b",
  },
  [LlmProvider.GUEST]: {
    fast: "groq/llama-3.3-8b-guest",
    main: "groq/llama-3.3-8b-guest",
    heavy: "groq/llama-3.3-8b-guest",
  },
};

export function StepLlm() {
  const router = useRouter();
  const storedProvider = useWizardStore((s) => s.llmProvider);
  const submitStep = useWizardStore((s) => s.submitStep);

  const initialCard: CardId = storedProvider
    ? storedProvider === LlmProvider.OLLAMA
      ? "local"
      : storedProvider === LlmProvider.GUEST
        ? "guest"
        : "byok"
    : "local";
  const [selected, setSelected] = useState<CardId>(initialCard);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* BYOK state */
  const initialByokProvider: LlmProvider =
    storedProvider && BYOK_PROVIDERS.includes(storedProvider)
      ? storedProvider
      : LlmProvider.ANTHROPIC;
  const [byokProvider, setByokProvider] = useState<LlmProvider>(initialByokProvider);
  const [apiKey, setApiKey] = useState<string>("");
  const [revealKey, setRevealKey] = useState(false);
  const [keyTestState, setKeyTestState] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [keyTestMessage, setKeyTestMessage] = useState<string>("");

  /* Ollama probe state */
  const [ollamaState, setOllamaState] = useState<"probing" | "ready" | "missing">("probing");
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaModel, setOllamaModel] = useState<string>("qwen2.5:7b");

  const requestIdRef = useRef<string>("");

  useEffect(() => {
    if (selected !== "local") return;
    const ws = getWsClient();
    const requestId = `ollama-${Date.now().toString(36)}`;
    requestIdRef.current = requestId;
    setOllamaState("probing");
    const unsub = ws.subscribe(ExtendedEventType.OLLAMA_PROBE_RESULT, (event) => {
      const data = event.data as {
        request_id?: string;
        reachable?: boolean;
        models?: string[];
      };
      if (data.request_id !== requestId) return;
      if (data.reachable) {
        setOllamaState("ready");
        setOllamaModels(data.models ?? []);
        if (data.models && data.models.length > 0 && !data.models.includes(ollamaModel)) {
          const first = data.models[0];
          if (first) setOllamaModel(first);
        }
      } else {
        setOllamaState("missing");
      }
    });
    ws.send(ExtendedEventType.OLLAMA_PROBE_REQUEST, { request_id: requestId });
    const timer = setTimeout(() => {
      if (requestIdRef.current === requestId) {
        setOllamaState((prev) => (prev === "probing" ? "missing" : prev));
      }
    }, 2_500);
    return () => {
      clearTimeout(timer);
      unsub();
    };
  }, [selected, ollamaModel]);

  const handleTestKey = async (): Promise<void> => {
    if (!apiKey.trim()) {
      setKeyTestState("error");
      setKeyTestMessage("Enter a key first.");
      return;
    }
    setKeyTestState("testing");
    setKeyTestMessage("");
    const ws = getWsClient();
    const requestId = `keytest-${Date.now().toString(36)}`;
    const unsub = ws.subscribe(ExtendedEventType.LLM_KEY_TEST_RESULT, (event) => {
      const data = event.data as {
        request_id?: string;
        success?: boolean;
        message?: string;
      };
      if (data.request_id !== requestId) return;
      unsub();
      if (data.success) {
        setKeyTestState("ok");
        setKeyTestMessage(data.message ?? "Key accepted.");
      } else {
        setKeyTestState("error");
        setKeyTestMessage(data.message ?? "Key rejected.");
      }
    });
    ws.send(ExtendedEventType.LLM_KEY_TEST_REQUEST, {
      request_id: requestId,
      provider: byokProvider,
      api_key: apiKey,
    });
    setTimeout(() => {
      setKeyTestState((prev) => (prev === "testing" ? "error" : prev));
      setKeyTestMessage((prev) => (prev ? prev : "Backend did not respond."));
    }, 15_000);
  };

  const handleContinue = async (): Promise<void> => {
    setError(null);
    if (selected === "local" && ollamaState !== "ready") {
      setError("Ollama isn't reachable. Install it or pick a different option.");
      return;
    }
    if (selected === "byok" && keyTestState !== "ok") {
      setError("Test your API key before continuing.");
      return;
    }

    let provider: LlmProvider;
    let tierMap: LlmTierMap;
    if (selected === "local") {
      provider = LlmProvider.OLLAMA;
      tierMap = {
        fast: `ollama/${ollamaModel}`,
        main: `ollama/${ollamaModel}`,
        heavy: `ollama/${ollamaModel}`,
      };
    } else if (selected === "byok") {
      provider = byokProvider;
      const fallback = DEFAULT_TIERS[LlmProvider.ANTHROPIC];
      if (!fallback) throw new Error("Missing default tier map for fallback");
      tierMap = DEFAULT_TIERS[byokProvider] ?? fallback;
    } else {
      provider = LlmProvider.GUEST;
      const fallback = DEFAULT_TIERS[LlmProvider.ANTHROPIC];
      if (!fallback) throw new Error("Missing default tier map for fallback");
      tierMap = DEFAULT_TIERS[LlmProvider.GUEST] ?? fallback;
    }

    setBusy(true);
    try {
      const result = await submitStep(WizardStepId.LLM, {
        llm_provider: provider,
        llm_tier_map: tierMap,
      });
      if (result.success) router.push("/onboarding/6-voice/");
      else if (result.error) setError(result.error);
    } finally {
      setBusy(false);
    }
  };

  return (
    <WizardStepShell
      step={WizardStepId.LLM}
      title="Pick the brain."
      subtitle="Your assistant needs a language model. Local runs private; cloud runs sharper."
      footer={
        <>
          <Button variant="ghost" onClick={() => router.push("/onboarding/4-name/")}>
            ← Back
          </Button>
          <Button size="lg" onClick={handleContinue} isLoading={busy}>
            Continue
          </Button>
        </>
      }
    >
      {error && <ErrorBanner message={error} />}
      <div role="radiogroup" aria-label="Language model source" className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <SelectableCard
          selected={selected === "local"}
          onClick={() => setSelected("local")}
          className="p-5"
        >
          <CardHeader eyebrow="Recommended" title="Free & Local" subtitle="Runs on your machine via Ollama." />
          <div className="mt-4 text-[12px] space-y-2">
            <OllamaStatusRow
              state={ollamaState}
              models={ollamaModels}
              selectedModel={ollamaModel}
              onChange={setOllamaModel}
            />
          </div>
        </SelectableCard>

        <SelectableCard
          selected={selected === "byok"}
          onClick={() => setSelected("byok")}
          className="p-5"
        >
          <CardHeader eyebrow="Best quality" title="Bring your own key" subtitle="Anthropic, OpenAI, Google, Groq, OpenRouter." />
          {selected === "byok" && (
            <div className="mt-4 space-y-3" onClick={(e) => e.stopPropagation()}>
              <div>
                <label className="block text-[11px] text-fg-muted mb-1">Provider</label>
                <Select
                  value={byokProvider}
                  onChange={(e) => {
                    setByokProvider(e.target.value as LlmProvider);
                    setKeyTestState("idle");
                    setKeyTestMessage("");
                  }}
                >
                  {BYOK_PROVIDERS.map((p) => (
                    <option key={p} value={p}>
                      {providerLabel(p)}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label className="block text-[11px] text-fg-muted mb-1">API key</label>
                <Input
                  type={revealKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setKeyTestState("idle");
                  }}
                  placeholder="sk-…"
                  autoComplete="off"
                  spellCheck={false}
                  trailing={
                    <button
                      type="button"
                      onClick={() => setRevealKey((r) => !r)}
                      className="text-[11px] text-fg-muted hover:text-fg-primary"
                    >
                      {revealKey ? "Hide" : "Show"}
                    </button>
                  }
                />
              </div>
              <TierMapPreview map={DEFAULT_TIERS[byokProvider] ?? DEFAULT_TIERS[LlmProvider.ANTHROPIC]!} />
              <div className="flex items-center gap-3">
                <Button size="sm" variant="secondary" onClick={handleTestKey} isLoading={keyTestState === "testing"}>
                  Test key
                </Button>
                <KeyTestStatus state={keyTestState} message={keyTestMessage} />
              </div>
              <a
                href={providerKeyUrl(byokProvider)}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-fg-muted hover:text-accent"
              >
                Where do I get a key?
              </a>
            </div>
          )}
        </SelectableCard>

        <SelectableCard
          selected={selected === "guest"}
          onClick={() => setSelected("guest")}
          className="p-5"
        >
          <CardHeader eyebrow="No setup" title="Guest mode" subtitle="Try Aether before committing." />
          <div className="mt-4 text-[12px] text-fg-muted leading-5">
            Uses a shared, rate-limited key (10 messages/hour). Great for kicking the tires.
          </div>
        </SelectableCard>
      </div>
    </WizardStepShell>
  );
}

function CardHeader({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
}) {
  return (
    <>
      <div className="text-[10px] uppercase tracking-[0.18em] text-accent/90">{eyebrow}</div>
      <div className="mt-1 text-[15px] font-medium text-fg-primary">{title}</div>
      <div className="text-[12px] text-fg-muted mt-1">{subtitle}</div>
    </>
  );
}

function OllamaStatusRow({
  state,
  models,
  selectedModel,
  onChange,
}: {
  state: "probing" | "ready" | "missing";
  models: string[];
  selectedModel: string;
  onChange(model: string): void;
}) {
  if (state === "probing") {
    return <span className="text-fg-muted">Checking for Ollama…</span>;
  }
  if (state === "missing") {
    return (
      <div className="space-y-1">
        <span className="text-warn">Ollama isn't running on this machine.</span>
        <div className="flex gap-2">
          <a
            href="https://ollama.com/download"
            target="_blank"
            rel="noreferrer"
            className="text-[11px] text-accent hover:underline"
          >
            Install Ollama →
          </a>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
      <span className="text-ok">Ollama reachable.</span>
      {models.length > 0 ? (
        <Select value={selectedModel} onChange={(e) => onChange(e.target.value)}>
          {models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </Select>
      ) : (
        <span className="text-fg-muted text-[11px]">
          No models installed. Run <code className="text-fg-secondary">ollama pull qwen2.5:7b</code>.
        </span>
      )}
    </div>
  );
}

function TierMapPreview({ map }: { map: LlmTierMap }) {
  return (
    <div className="text-[11px] text-fg-muted leading-5 space-y-0.5">
      <div>
        Fast: <span className="text-fg-secondary">{map.fast}</span>
      </div>
      <div>
        Main: <span className="text-fg-secondary">{map.main}</span>
      </div>
      <div>
        Heavy: <span className="text-fg-secondary">{map.heavy}</span>
      </div>
    </div>
  );
}

function KeyTestStatus({ state, message }: { state: "idle" | "testing" | "ok" | "error"; message: string }) {
  if (state === "idle") return null;
  const cls =
    state === "ok" ? "text-ok" : state === "error" ? "text-error" : "text-fg-muted";
  return <span className={`text-[11px] ${cls}`}>{message || (state === "testing" ? "Testing…" : "")}</span>;
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="mb-4 px-4 py-2 rounded-md border border-error/50 bg-error/10 text-error text-[12px]"
    >
      {message}
    </div>
  );
}

function providerLabel(p: LlmProvider): string {
  switch (p) {
    case LlmProvider.ANTHROPIC:
      return "Anthropic";
    case LlmProvider.OPENAI:
      return "OpenAI";
    case LlmProvider.GOOGLE:
      return "Google";
    case LlmProvider.GROQ:
      return "Groq";
    case LlmProvider.OPENROUTER:
      return "OpenRouter";
    case LlmProvider.OLLAMA:
      return "Ollama (local)";
    case LlmProvider.GUEST:
      return "Guest mode";
    default:
      return p;
  }
}

function providerKeyUrl(p: LlmProvider): string {
  switch (p) {
    case LlmProvider.ANTHROPIC:
      return "https://console.anthropic.com/settings/keys";
    case LlmProvider.OPENAI:
      return "https://platform.openai.com/api-keys";
    case LlmProvider.GOOGLE:
      return "https://aistudio.google.com/app/apikey";
    case LlmProvider.GROQ:
      return "https://console.groq.com/keys";
    case LlmProvider.OPENROUTER:
      return "https://openrouter.ai/keys";
    default:
      return "https://ollama.com/";
  }
}
