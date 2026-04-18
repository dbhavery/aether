import {
  forwardRef,
  type ForwardedRef,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
  children: ReactNode;
}

/**
 * Native <select> styled to match Input. Native beats a custom listbox for
 * accessibility unless we have a hard reason to build one.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { invalid = false, className, children, ...rest }: SelectProps,
  ref: ForwardedRef<HTMLSelectElement>,
) {
  return (
    <div
      className={[
        "flex items-center rounded-md border bg-bg-1 h-10 px-3",
        invalid ? "border-error" : "border-border-default focus-within:border-accent",
      ].join(" ")}
      style={{ boxShadow: "var(--shadow-inset)" }}
    >
      <select
        ref={ref}
        aria-invalid={invalid || undefined}
        className={[
          "flex-1 bg-transparent text-[13px] text-fg-primary focus:outline-none",
          "appearance-none pr-6",
          className ?? "",
        ].join(" ")}
        {...rest}
      >
        {children}
      </select>
      <svg
        aria-hidden
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="text-fg-muted -ml-4 pointer-events-none"
      >
        <path d="M1.5 3L5 6.5L8.5 3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
});
