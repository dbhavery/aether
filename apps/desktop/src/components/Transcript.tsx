import { useEffect, useRef } from "react";

import type { MessageMeta, TranscriptMessage } from "../lib/types";

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
 *   - provider          (e.g. "ollama", "stub-echo")
 *   - latency_ms        → "1.4s" or "820ms"
 *   - tokens            → "42 tok" when either count is present;
 *                         "p123/c45 tok" when both are present.
 *
 * Returns null if there's nothing to show — keeps the DOM clean for
 * stubbed responses that carry no meta at all.
 */
function MessageMetaFooter({ meta }: { meta: MessageMeta }) {
  const parts: string[] = [];
  if (meta.tier) parts.push(meta.tier);
  if (meta.provider) parts.push(meta.provider);
  if (typeof meta.latency_ms === "number") parts.push(formatLatency(meta.latency_ms));
  const tokenStr = formatTokens(meta.prompt_tokens, meta.completion_tokens);
  if (tokenStr) parts.push(tokenStr);
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
