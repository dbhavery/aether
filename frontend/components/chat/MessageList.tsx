"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/stores/chat";

export function MessageList({
  messages,
  assistantLabel,
  userLabel,
}: {
  messages: ChatMessage[];
  assistantLabel: string;
  userLabel?: string;
}) {
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6">
      <div className="max-w-3xl mx-auto space-y-6">
        {messages.map((m) => (
          <MessageBubble
            key={m.id}
            message={m}
            assistantLabel={assistantLabel}
            userLabel={userLabel ?? "You"}
          />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  assistantLabel,
  userLabel,
}: {
  message: ChatMessage;
  assistantLabel: string;
  userLabel: string;
}) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  if (isSystem) {
    return (
      <div className="text-center text-[12px] text-error/90 border border-error/30 bg-error/5 rounded-md py-2 px-3">
        {message.content}
      </div>
    );
  }

  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}>
      <div className="text-[11px] uppercase tracking-[0.14em] text-fg-muted mb-1.5">
        {isUser ? userLabel : assistantLabel}
      </div>
      <div
        className={[
          "max-w-[80%] rounded-[var(--radius-lg)] px-4 py-3 leading-6 text-[14px] whitespace-pre-wrap",
          isUser
            ? "bg-accent/10 border border-accent/30 text-fg-primary"
            : "bg-bg-2 border border-border-subtle text-fg-primary",
        ].join(" ")}
        style={{ boxShadow: "var(--shadow-raised)" }}
      >
        {message.content}
        {message.streaming && <StreamingCursor />}
      </div>
    </div>
  );
}

function StreamingCursor() {
  return (
    <span
      aria-hidden
      className="inline-block w-1.5 h-4 align-middle ml-1 bg-accent animate-pulse"
    />
  );
}
