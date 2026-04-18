import {
  forwardRef,
  type ForwardedRef,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  trailing?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid = false, trailing, className, type = "text", ...rest }: InputProps,
  ref: ForwardedRef<HTMLInputElement>,
) {
  return (
    <div
      className={[
        "group relative flex items-center rounded-md border bg-bg-1 px-3 h-10",
        invalid ? "border-error" : "border-border-default focus-within:border-accent",
        "transition-colors duration-150",
      ].join(" ")}
      style={{ boxShadow: "var(--shadow-inset)" }}
    >
      <input
        ref={ref}
        type={type}
        aria-invalid={invalid || undefined}
        className={[
          "flex-1 bg-transparent text-[13px] text-fg-primary placeholder:text-fg-muted",
          "focus:outline-none",
          className ?? "",
        ].join(" ")}
        {...rest}
      />
      {trailing && <div className="ml-2 flex items-center">{trailing}</div>}
    </div>
  );
});
