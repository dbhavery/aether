"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/Button";

export interface ChatInputProps {
  disabled?: boolean;
  placeholder?: string;
  onSubmit(text: string): void;
}

/**
 * Auto-sizing textarea + send button. Enter submits, Shift+Enter adds a
 * newline. Height grows up to a hard cap so a paste-bomb can't eat the
 * whole chat.
 */
export function ChatInput({ disabled = false, placeholder, onSubmit }: ChatInputProps) {
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const [value, setValue] = useState("");

  const submit = (): void => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setValue("");
    if (taRef.current) taRef.current.style.height = "auto";
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const handleInput = (): void => {
    if (!taRef.current) return;
    taRef.current.style.height = "auto";
    taRef.current.style.height = `${Math.min(taRef.current.scrollHeight, 200)}px`;
  };

  return (
    <form
      className="border-t border-border-subtle bg-bg-0 px-6 py-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div
        className="max-w-3xl mx-auto flex items-end gap-3 rounded-[var(--radius-lg)] bg-bg-1 border border-border-default px-3 py-2"
        style={{ boxShadow: "var(--shadow-inset)" }}
      >
        <textarea
          ref={taRef}
          rows={1}
          value={value}
          placeholder={placeholder ?? "Message your assistant"}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onInput={handleInput}
          onKeyDown={handleKey}
          className="flex-1 bg-transparent text-[14px] text-fg-primary placeholder:text-fg-muted resize-none focus:outline-none py-2"
          aria-label="Message input"
        />
        <Button type="submit" disabled={disabled || !value.trim()} size="md">
          Send
        </Button>
      </div>
      <p className="max-w-3xl mx-auto mt-2 text-[11px] text-fg-muted">
        Enter to send · Shift+Enter for a newline
      </p>
    </form>
  );
}
