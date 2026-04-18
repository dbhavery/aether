/**
 * CSS-only persona portrait placeholder.
 *
 * Real avatar art doesn't exist yet, but we need the wizard grid to still
 * feel lived-in. Each portrait takes its first letter and a per-persona hue
 * and renders a soft radial-gradient disc + initial. Keyed to persona id so
 * Aurora and Atlas don't look identical.
 */

export interface PersonaPortraitProps {
  id: string;
  displayName: string;
  hue: number;
  size?: number;
  /** Subtle glow / scale when the card is being hovered upstream. */
  animated?: boolean;
}

export function PersonaPortrait({
  id,
  displayName,
  hue,
  size = 96,
  animated = false,
}: PersonaPortraitProps) {
  const initial = displayName.charAt(0).toUpperCase();
  return (
    <div
      role="img"
      aria-label={`${displayName} portrait placeholder`}
      className="relative rounded-full overflow-hidden flex items-center justify-center select-none"
      style={{
        width: size,
        height: size,
        background: `radial-gradient(70% 70% at 32% 28%, hsl(${hue} 55% 40% / 0.85) 0%, hsl(${hue} 40% 15% / 0.95) 55%, hsl(${hue} 30% 8% / 1) 100%)`,
        boxShadow:
          "0 1px 0 rgba(255,255,255,0.05) inset, 0 -4px 12px rgba(0,0,0,0.5) inset, 0 4px 16px rgba(0,0,0,0.45)",
        transition: "transform 260ms var(--ease-out), filter 260ms var(--ease-out)",
        transform: animated ? "scale(1.02)" : undefined,
        filter: animated ? `brightness(1.08) saturate(1.05)` : undefined,
      }}
      data-persona-id={id}
    >
      <span
        className="font-medium text-fg-primary/90"
        style={{ fontSize: size * 0.42, letterSpacing: "-0.04em" }}
      >
        {initial}
      </span>
      <span
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(120% 90% at 50% 120%, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0) 55%)",
        }}
      />
    </div>
  );
}
