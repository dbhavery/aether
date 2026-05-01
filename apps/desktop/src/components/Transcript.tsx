import { useEffect, useRef } from "react";

import type { MessageMeta, TranscriptMessage } from "../lib/types";
import { isVisionProvider } from "../lib/visionProviders";

interface Props {
  messages: TranscriptMessage[];
}

export function Transcript({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  return (
    <div className="allow-select flex-1 overflow-y-auto px-6 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} aria-hidden />
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: TranscriptMessage }) {
  if (message.role === "user") {
    return (
      <div className="self-end max-w-[85%] rounded-lg rounded-br-sm bg-aether-elevated px-4 py-2.5 text-[13.5px] text-aether-text shadow-neu animate-fadeIn">
        {message.content}
      </div>
    );
  }
  if (message.role === "system") {
    if (message.variant === "draft_only") {
      // Wave 16 — DeferToDraft Turn-path affordance. Distinct amber
      // styling + a "DRAFT ONLY" badge cue the user that the engine
      // recorded the intent (Decision::DraftOnly { source: UserChoice })
      // but suppressed any side effect. The Rust-side audit row carries
      // the truth; this is purely the chat-surface affordance.
      return (
        <div
          data-testid="draft-only-bubble"
          className="self-center max-w-[85%] rounded-md border border-aether-warn/60 bg-aether-warn/10 px-3 py-2 text-center animate-fadeIn"
        >
          <div className="mb-1 inline-block rounded-sm border border-aether-warn/70 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.18em] text-aether-warn">
            Draft only
          </div>
          <div className="text-[11.5px] font-mono leading-snug text-aether-muted">
            {message.content}
          </div>
        </div>
      );
    }
    return (
      <div className="self-center max-w-[85%] rounded-md border border-aether-border bg-aether-bg/60 px-3 py-1.5 text-center text-[11.5px] font-mono text-aether-muted animate-fadeIn">
        {message.content}
      </div>
    );
  }
  // assistant
  return renderAssistant(message);
}

function renderAssistant(message: TranscriptMessage) {
  return (
    <div className="self-start max-w-[90%] animate-fadeIn">
      <div className="rounded-lg rounded-bl-sm neu-surface px-4 py-3 text-[13.5px] leading-relaxed text-aether-text whitespace-pre-wrap">
        {message.content}
      </div>
      {message.meta && <MessageMetaFooter meta={message.meta} />}
    </div>
  );
}

/**
 * Assistant-message meta-footer. Renders the pieces the router surfaced
 * for this turn, space-dot-separated. Each piece is opt-in:
 *   - tier              (e.g. "reflex", "local-small")
 *   - provider          (e.g. "ollama", "ollama-vision")
 *   - model             (e.g. "llava:latest" — vision turns only)
 *   - latency_ms        → "1.4s" or "820ms"
 *   - tokens            → "42 tok" when either count is present;
 *                         "p123/c45 tok" when both are present.
 *
 * Returns null if there's nothing to show — keeps the DOM clean for
 * stubbed responses that carry no meta at all.
 */
function MessageMetaFooter({ meta }: { meta: MessageMeta }) {
  const parts = buildMetaParts(meta);
  if (parts.length === 0) return null;
  return (
    <div className="mt-1 pl-1 text-[10.5px] font-mono text-aether-dim">
      {parts.map((p, i) => (
        <span key={i}>
          {i > 0 && <span className="mx-1 text-aether-border">·</span>}
          <span>{p}</span>
        </span>
      ))}
    </div>
  );
}

/**
 * Pure helper that turns a `MessageMeta` into the ordered list of
 * footer chips. Exposed for unit tests so the inclusion / ordering /
 * formatting can be locked without rendering React.
 *
 * Order is fixed: tier · provider · model · latency · tokens. The
 * model chip is included only when `meta.model` is a non-empty
 * string — keeps the footer honest for text-only turns where vision
 * didn't run. The tier chip is dropped on vision turns (see
 * [`tierChipForFooter`]) because the long vision tier label
 * (`"Ollama vision · llava · http://..."`) duplicates the
 * provider+model chips that follow.
 */
export function buildMetaParts(meta: MessageMeta): string[] {
  const parts: string[] = [];
  const originChip = originChipForFooter(meta);
  if (originChip) parts.push(originChip);
  const tier = tierChipForFooter(meta);
  if (tier) parts.push(tier);
  if (meta.provider) parts.push(meta.provider);
  if (typeof meta.model === "string" && meta.model.trim().length > 0) {
    parts.push(meta.model);
  }
  if (typeof meta.latency_ms === "number") {
    parts.push(formatLatency(meta.latency_ms));
  }
  const tokenStr = formatTokens(meta.prompt_tokens, meta.completion_tokens);
  if (tokenStr) parts.push(tokenStr);
  return parts;
}

/**
 * Modality chip for the transcript footer. Surfaces which capture
 * path the turn came from — `"voice"` for push-to-talk, `"vision"`
 * for camera/screen. Text-only turns have no origin and return
 * null. Pure: exposed for unit tests.
 */
export function originChipForFooter(meta: MessageMeta): string | null {
  if (meta.origin === "voice") return "voice";
  if (meta.origin === "vision") return "vision";
  return null;
}

/**
 * Decide what (if anything) the tier chip should show in the
 * transcript footer.
 *
 * - Text-only turns (`provider` is not a known vision id) keep their
 *   tier as-is — for the reflex / Ollama text path it's a meaningful
 *   summary like `"local"` or `"reflex-stub"`.
 * - Vision turns (`provider` ∈ `VISION_PROVIDER_IDS`) drop the tier
 *   entirely, because the Rust `maybe_apply_vision` substitution
 *   pushes the long provider label
 *   (`"Ollama vision · llava:latest · http://127.0.0.1:11434"`) into
 *   `tier`, and the dedicated provider + model chips that follow
 *   already cover that information without the URL noise.
 *
 * Returns `null` to signal "no tier chip"; otherwise returns the
 * exact string to render. Pure: exposed for unit tests.
 */
export function tierChipForFooter(meta: MessageMeta): string | null {
  if (!meta.tier) return null;
  if (isVisionProvider(meta.provider)) return null;
  return meta.tier;
}

function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTokens(
  prompt: number | undefined,
  completion: number | undefined,
): string | null {
  const hasP = typeof prompt === "number";
  const hasC = typeof completion === "number";
  if (hasP && hasC) return `p${prompt}/c${completion} tok`;
  if (hasC) return `${completion} tok`;
  if (hasP) return `${prompt} tok`;
  return null;
}
