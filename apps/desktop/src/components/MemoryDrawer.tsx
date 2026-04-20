import { useEffect, useState } from "react";

import { memoryRecent } from "../lib/api";
import type { TranscriptMessage } from "../lib/types";

interface Props {
  open: boolean;
  refreshKey: number;
  onClose: () => void;
}

/**
 * Small memory inspector — "what do you remember about me (right now)?"
 * per planning/10_memory_architecture §Memory governance. v0 shows the
 * session-only transcript window. Durable-memory inspection is a later
 * slice.
 */
export function MemoryDrawer({ open, refreshKey, onClose }: Props) {
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    memoryRecent()
      .then((rows) => {
        if (!cancelled) setMessages(rows);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open, refreshKey]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-sm flex-col border-l border-aether-border bg-aether-surface shadow-neuRaised animate-fadeIn"
      role="complementary"
      aria-label="Session memory"
    >
      <div className="flex items-center justify-between border-b border-aether-border px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Memory · session
          </div>
          <div className="text-[13px] text-aether-text">
            What Aether remembers right now
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
      <div className="allow-select flex-1 overflow-y-auto px-5 py-4 text-[12.5px]">
        {err && <div className="text-aether-err">{err}</div>}
        {!err && messages.length === 0 && (
          <div className="mt-6 text-center text-aether-muted">
            Nothing in this session yet. Send a message and it will appear here.
          </div>
        )}
        <div className="flex flex-col gap-3">
          {messages.map((m) => (
            <div
              key={m.id}
              className="rounded-md border border-aether-border bg-aether-bg/50 px-3 py-2"
            >
              <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-aether-dim">
                <span>{m.role}</span>
                <span>#{m.sequence}</span>
              </div>
              <div className="mt-1 whitespace-pre-wrap text-aether-text">
                {m.content}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="border-t border-aether-border px-5 py-3 text-[11px] text-aether-muted">
        Durable memory inspection, editing, and export are on the roadmap.
        Nothing here persists beyond this app session.
      </div>
    </div>
  );
}
