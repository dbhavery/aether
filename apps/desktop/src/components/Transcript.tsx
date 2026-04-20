import { useEffect, useRef } from "react";

import type { TranscriptMessage } from "../lib/types";

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
  return (
    <div className="self-start max-w-[90%] animate-fadeIn">
      <div className="rounded-lg rounded-bl-sm neu-surface px-4 py-3 text-[13.5px] leading-relaxed text-aether-text whitespace-pre-wrap">
        {message.content}
      </div>
      {message.meta && (message.meta.tier || message.meta.provider) && (
        <div className="mt-1 pl-1 text-[10.5px] font-mono text-aether-dim">
          {message.meta.tier && <span>{message.meta.tier}</span>}
          {message.meta.tier && message.meta.provider && (
            <span className="mx-1 text-aether-border">·</span>
          )}
          {message.meta.provider && <span>{message.meta.provider}</span>}
        </div>
      )}
    </div>
  );
}
