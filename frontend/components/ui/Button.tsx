"use client";

import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ForwardedRef,
  type ReactNode,
} from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-black hover:bg-accent-hover disabled:bg-bg-3 disabled:text-fg-disabled shadow-[var(--shadow-raised)]",
  secondary:
    "bg-bg-2 text-fg-primary hover:bg-bg-3 border border-border-default disabled:text-fg-disabled",
  ghost:
    "bg-transparent text-fg-secondary hover:text-fg-primary hover:bg-bg-2 disabled:text-fg-disabled",
  danger:
    "bg-error/90 text-black hover:bg-error disabled:bg-bg-3 disabled:text-fg-disabled",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[12px]",
  md: "h-10 px-4 text-[13px]",
  lg: "h-12 px-6 text-[14px]",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    isLoading = false,
    leadingIcon,
    trailingIcon,
    disabled,
    className,
    children,
    type,
    ...rest
  }: ButtonProps,
  ref: ForwardedRef<HTMLButtonElement>,
) {
  const disabledState = disabled || isLoading;
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      disabled={disabledState}
      aria-busy={isLoading}
      className={[
        "inline-flex items-center justify-center gap-2 font-medium tracking-tight rounded-md",
        "transition-colors duration-150 ease-out",
        "focus-visible:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-80",
        SIZE_CLASSES[size],
        VARIANT_CLASSES[variant],
        className ?? "",
      ].join(" ")}
      {...rest}
    >
      {leadingIcon && <span className="shrink-0">{leadingIcon}</span>}
      {isLoading ? <Spinner /> : children}
      {trailingIcon && <span className="shrink-0">{trailingIcon}</span>}
    </button>
  );
});

function Spinner() {
  return (
    <span
      className="inline-block w-3.5 h-3.5 rounded-full border-2 border-current border-r-transparent animate-spin"
      aria-hidden
    />
  );
}
