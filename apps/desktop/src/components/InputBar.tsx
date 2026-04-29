import { useEffect, useRef, useState } from "react";

interface Props {
  disabled?: boolean;
  placeholder?: string;
  onSubmit: (text: string) => void;
}

export function InputBar({ disabled, placeholder, onSubmit }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+K / Cmd+K focuses the input.
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (!disabled) ref.current?.focus();
  }, [disabled]);

  const submit = () => {
    const text = value.trim();
    if (!text || disabled) return;
    onSubmit(text);
    setValue("");
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-aether-border bg-aether-bg px-6 py-4">
      <div className="mx-auto flex max-w-2xl items-end gap-2">
        <div className="neu-inset flex-1 rounded-lg">
          <textarea
            ref={ref}
            disabled={disabled}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder={placeholder || "Message Companion…"}
            className="allow-select w-full resize-none bg-transparent px-4 py-3 text-[13.5px] text-aether-text placeholder:text-aether-dim focus:outline-none disabled:opacity-50"
            style={{ minHeight: "44px", maxHeight: "160px" }}
          />
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !value.trim()}
          className="rounded-md border border-aether-borderHi bg-aether-elevated px-4 py-2.5 text-[12.5px] text-aether-text transition-colors hover:border-aether-text disabled:cursor-not-allowed disabled:opacity-40"
        >
          Send
        </button>
      </div>
      <div className="mx-auto mt-1.5 flex max-w-2xl items-center justify-between gap-3 text-[10.5px] font-mono text-aether-dim">
        <span className="truncate">
          Try <span className="text-aether-text">read /tmp/x</span>,{" "}
          <span className="text-aether-text">write /tmp/x</span>, or{" "}
          <span className="text-aether-text">shell ls</span> to exercise policy.
        </span>
        <span className="shrink-0">Enter send · Shift+Enter newline · Ctrl+K focus</span>
      </div>
    </div>
  );
}
