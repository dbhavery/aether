"use client";

import { useId, type ChangeEvent, type ReactNode } from "react";

export interface CheckboxProps {
  checked: boolean;
  onChange(checked: boolean): void;
  children: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  id?: string;
}

/**
 * Accessible checkbox with label + optional description. The native input is
 * visually hidden but remains the target of clicks/keys so screen readers and
 * form submission both behave.
 */
export function Checkbox({
  checked,
  onChange,
  children,
  description,
  disabled = false,
  id,
}: CheckboxProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const handle = (e: ChangeEvent<HTMLInputElement>): void => {
    onChange(e.target.checked);
  };

  return (
    <label
      htmlFor={inputId}
      className={[
        "flex gap-3 items-start cursor-pointer select-none",
        disabled ? "opacity-60 cursor-not-allowed" : "",
      ].join(" ")}
    >
      <span className="relative flex items-center mt-0.5 w-4 h-4">
        <input
          id={inputId}
          type="checkbox"
          checked={checked}
          onChange={handle}
          disabled={disabled}
          className="peer absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed z-10"
        />
        <span
          aria-hidden
          className={[
            "pointer-events-none w-4 h-4 rounded-[4px] border transition-colors duration-150 flex items-center justify-center",
            checked
              ? "bg-accent border-accent"
              : "bg-bg-1 border-border-strong peer-focus-visible:ring-2 peer-focus-visible:ring-accent-ring",
          ].join(" ")}
        >
          {checked && (
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M2 5.2L4 7.4L8 2.6"
                stroke="#0a0a0a"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </span>
      </span>
      <span className="text-[13px] leading-5">
        <span className="text-fg-primary">{children}</span>
        {description && <span className="block text-fg-muted mt-0.5">{description}</span>}
      </span>
    </label>
  );
}
