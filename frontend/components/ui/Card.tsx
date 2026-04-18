import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
  selected?: boolean;
  children: ReactNode;
}

/**
 * Surface primitive. `interactive` adds a subtle hover lift; `selected`
 * applies the accent ring + check state used across the wizard.
 */
export function Card({
  interactive = false,
  selected = false,
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={[
        "relative rounded-[var(--radius-lg)] bg-bg-2 border border-border-default",
        "transition-transform duration-[var(--dur-med)] ease-[var(--ease-out)]",
        interactive ? "hover:-translate-y-0.5 hover:border-border-strong cursor-pointer" : "",
        selected ? "ring-1 ring-accent border-accent" : "",
        className ?? "",
      ].join(" ")}
      style={{ boxShadow: interactive || selected ? "var(--shadow-raised)" : undefined }}
      aria-pressed={interactive ? selected : undefined}
      {...rest}
    >
      {children}
      {selected && <SelectedBadge />}
    </div>
  );
}

export interface SelectableCardProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onSelect"> {
  selected?: boolean;
  children: ReactNode;
}

/**
 * Like Card, but rendered as a <button> so the browser makes it keyboard-
 * focusable and announces selection state. Use wherever a card doubles as
 * a radio in a group (wizard avatar/personality grids, LLM/voice cards).
 */
export function SelectableCard({
  selected = false,
  disabled,
  className,
  children,
  ...rest
}: SelectableCardProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      className={[
        "relative text-left rounded-[var(--radius-lg)] bg-bg-2 border",
        "transition-all duration-[var(--dur-med)] ease-[var(--ease-out)]",
        "focus-visible:outline-none",
        selected ? "border-accent ring-1 ring-accent" : "border-border-default hover:border-border-strong",
        disabled ? "opacity-60 cursor-not-allowed" : "hover:-translate-y-0.5 cursor-pointer",
        className ?? "",
      ].join(" ")}
      style={{ boxShadow: selected ? "var(--shadow-raised)" : "none" }}
      {...rest}
    >
      {children}
      {selected && <SelectedBadge />}
    </button>
  );
}

function SelectedBadge() {
  return (
    <span
      aria-hidden
      className="absolute top-2 right-2 w-5 h-5 rounded-full bg-accent text-black flex items-center justify-center text-[11px]"
      style={{ boxShadow: "var(--shadow-raised)" }}
    >
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M2 5.2L4 7.4L8 2.6"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
