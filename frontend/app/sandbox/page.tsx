"use client";

import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Select } from "@/components/ui/Select";
import { PERSONAS, findPersona } from "@/lib/personas";
import { useSessionStore } from "@/lib/stores/session";
import { useWizardStore } from "@/lib/stores/wizard";
import { getWsClient } from "@/lib/ws";
import { EventType, LlmProvider } from "@/lib/types";

const TABS = [
  { id: "persona", label: "Persona" },
  { id: "llm", label: "LLM" },
  { id: "voice", label: "Voice" },
  { id: "memory", label: "Memory" },
  { id: "appearance", label: "Appearance" },
  { id: "about", label: "About" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function SandboxPage() {
  const [active, setActive] = useState<TabId>("persona");

  return (
    <div className="h-full flex flex-col">
      <div className="border-b border-border-subtle px-6">
        <nav role="tablist" aria-label="Sandbox sections" className="flex gap-1">
          {TABS.map((t) => {
            const selected = active === t.id;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={selected}
                onClick={() => setActive(t.id)}
                className={[
                  "px-4 py-3 text-[12px] tracking-wide transition-colors duration-150",
                  selected
                    ? "text-fg-primary border-b border-accent"
                    : "text-fg-muted hover:text-fg-secondary border-b border-transparent",
                ].join(" ")}
              >
                {t.label}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">
          {active === "persona" && <PersonaTab />}
          {active === "llm" && <LlmTab />}
          {active === "voice" && <VoiceTab />}
          {active === "memory" && <MemoryTab />}
          {active === "appearance" && <AppearanceTab />}
          {active === "about" && <AboutTab />}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Persona tab                                                                */
/* -------------------------------------------------------------------------- */

function PersonaTab() {
  const activeId = useSessionStore((s) => s.activePersonaId);
  const setActive = useSessionStore((s) => s.setActivePersona);
  const switchPersona = (id: string): void => {
    const persona = findPersona(id);
    setActive(id, persona?.displayName ?? id);
    getWsClient().send(EventType.PERSONA_CHANGED, { persona_id: id });
  };
  const current = activeId ? findPersona(activeId) : undefined;
  return (
    <Section
      title="Persona packs"
      subtitle={`Switch between bundled personas. ${PERSONAS.length} loaded.`}
    >
      <div className="mb-6 p-4 rounded-[var(--radius-md)] bg-bg-2 border border-border-subtle flex items-center gap-4">
        <PersonaSwatch hue={current?.hue ?? 0} initial={current?.displayName?.[0] ?? "—"} size={40} />
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-[0.14em] text-fg-muted">Active</div>
          <div className="mt-1 text-[15px] font-medium truncate">
            {current?.displayName ?? "None selected"}
          </div>
          <div className="text-[12px] text-fg-muted mt-1 truncate">
            {current?.tagline ?? "Pick one below to start talking."}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {PERSONAS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => switchPersona(p.id)}
            className={[
              "text-left p-3 rounded-md border transition-colors duration-150 flex items-start gap-3",
              activeId === p.id
                ? "border-accent bg-accent/5 text-fg-primary"
                : "border-border-subtle hover:border-border-strong bg-bg-2 text-fg-secondary",
            ].join(" ")}
          >
            <PersonaSwatch hue={p.hue} initial={p.displayName[0] ?? "?"} size={28} />
            <div className="min-w-0">
              <div className="text-[13px] font-medium">{p.displayName}</div>
              <div className="text-[11px] text-fg-muted mt-0.5">{p.tagline}</div>
            </div>
          </button>
        ))}
      </div>
      <p className="text-[12px] text-fg-muted mt-6">
        Drop a custom pack into <code className="text-fg-secondary">%APPDATA%/aether/personas/</code> and it'll show up here on next launch.
      </p>
    </Section>
  );
}

function PersonaSwatch({ hue, initial, size }: { hue: number; initial: string; size: number }) {
  return (
    <div
      aria-hidden
      className="rounded-full flex items-center justify-center shrink-0 text-fg-primary font-medium"
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.42),
        background: `radial-gradient(60% 60% at 30% 30%, hsl(${hue} 65% 60%) 0%, hsl(${hue} 55% 30%) 70%)`,
        boxShadow: "var(--shadow-raised)",
      }}
    >
      {initial.toUpperCase()}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* LLM tab                                                                    */
/* -------------------------------------------------------------------------- */

function LlmTab() {
  const provider = useWizardStore((s) => s.llmProvider);
  const tierMap = useWizardStore((s) => s.llmTierMap);
  const [budget, setBudget] = useState<string>("25");
  return (
    <Section title="Language model" subtitle="Active provider, tier mapping, and a soft monthly budget.">
      <Row label="Provider">
        <span className="text-fg-primary">{provider ?? "Not configured"}</span>
      </Row>
      <Row label="Fast tier">
        <span className="text-fg-secondary">{tierMap?.fast ?? "—"}</span>
      </Row>
      <Row label="Main tier">
        <span className="text-fg-secondary">{tierMap?.main ?? "—"}</span>
      </Row>
      <Row label="Heavy tier">
        <span className="text-fg-secondary">{tierMap?.heavy ?? "—"}</span>
      </Row>
      <Row label="Change provider">
        <Select
          value={provider ?? LlmProvider.OLLAMA}
          onChange={(e) => {
            const next = e.target.value as LlmProvider;
            getWsClient().send(EventType.PROVIDER_CHANGED, { provider: next });
          }}
        >
          {Object.values(LlmProvider).map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </Select>
      </Row>
      <Row label="Monthly budget (USD)">
        <input
          type="number"
          min={0}
          max={9999}
          value={budget}
          onChange={(e) => setBudget(e.target.value)}
          className="w-28 h-10 bg-bg-1 border border-border-default rounded-md px-3 text-[13px] text-fg-primary"
        />
      </Row>
      <p className="text-[12px] text-fg-muted mt-4">
        Usage stats ship with the first cloud provider you configure.
      </p>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Voice tab                                                                  */
/* -------------------------------------------------------------------------- */

function VoiceTab() {
  const mode = useWizardStore((s) => s.voiceMode);
  const testMic = (): void => {
    getWsClient().send("voice_test_mic_request", {});
  };
  return (
    <Section title="Voice" subtitle="Speech in, speech out. Hardware probe runs on demand.">
      <Row label="Mode">
        <span className="text-fg-primary">{mode ?? "Not configured"}</span>
      </Row>
      <Row label="Test microphone">
        <Button size="sm" variant="secondary" onClick={testMic}>
          Speak for 2 seconds
        </Button>
      </Row>
      <p className="text-[12px] text-fg-muted mt-4">
        Change provider or toggle off from the section above. ElevenLabs usage will appear here
        once connected.
      </p>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Memory tab                                                                 */
/* -------------------------------------------------------------------------- */

function MemoryTab() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const activeId = useSessionStore((s) => s.activePersonaId);
  const clear = (): void => {
    if (!activeId) return;
    getWsClient().send("memory_clear_persona", { persona_id: activeId });
    setConfirmOpen(false);
  };
  return (
    <Section title="Memory" subtitle="Per-persona memory is isolated by default.">
      <Row label="Storage used">
        <span className="text-fg-secondary">Reported by backend on next health cycle.</span>
      </Row>
      <Row label="Active persona">
        <span className="text-fg-secondary">{activeId ?? "None"}</span>
      </Row>
      <Row label="Clear memory">
        {confirmOpen ? (
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-warn">Really wipe everything?</span>
            <Button size="sm" variant="danger" onClick={clear}>
              Yes, clear
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => setConfirmOpen(true)} disabled={!activeId}>
            Clear all memory for {activeId ?? "persona"}
          </Button>
        )}
      </Row>
      <Row label="Export">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => getWsClient().send("memory_export_request", { persona_id: activeId })}
          disabled={!activeId}
        >
          Download as JSON
        </Button>
      </Row>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Appearance tab                                                             */
/* -------------------------------------------------------------------------- */

function AppearanceTab() {
  const [alwaysOnTop, setAlwaysOnTop] = useState(false);
  const [fontSize, setFontSize] = useState<"sm" | "md" | "lg">("md");
  return (
    <Section title="Appearance" subtitle="Dark theme only in v1.0. More controls post-launch.">
      <Row label="Theme">
        <span className="text-fg-secondary">Dark (only option in v1.0)</span>
      </Row>
      <Row label="Always on top">
        <Checkbox checked={alwaysOnTop} onChange={setAlwaysOnTop}>
          Keep the window above others
        </Checkbox>
      </Row>
      <Row label="Font size">
        <Select value={fontSize} onChange={(e) => setFontSize(e.target.value as typeof fontSize)}>
          <option value="sm">Small</option>
          <option value="md">Medium</option>
          <option value="lg">Large</option>
        </Select>
      </Row>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* About tab                                                                  */
/* -------------------------------------------------------------------------- */

function AboutTab() {
  return (
    <Section title="About" subtitle="License, docs, version.">
      <Row label="Version">
        <span className="text-fg-secondary">Aether 1.0.0 (dev)</span>
      </Row>
      <Row label="License">
        <span className="text-fg-secondary">MIT</span>
      </Row>
      <Row label="Docs">
        <a
          href="https://github.com/dbhavery/aether"
          target="_blank"
          rel="noreferrer"
          className="text-accent hover:underline"
        >
          GitHub →
        </a>
      </Row>
    </Section>
  );
}

/* -------------------------------------------------------------------------- */
/* Layout helpers                                                             */
/* -------------------------------------------------------------------------- */

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <h2 className="text-[20px] font-medium tracking-tight">{title}</h2>
      {subtitle && <p className="text-[13px] text-fg-muted mt-1">{subtitle}</p>}
      <div className="mt-6 divide-y divide-border-subtle">{children}</div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 py-3 text-[13px]">
      <div className="text-fg-muted shrink-0 w-40">{label}</div>
      <div className="flex-1 flex items-center justify-end">{children}</div>
    </div>
  );
}
