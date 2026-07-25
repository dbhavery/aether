/**
 * Persona portrait — loads the real AI-generated portrait from the backend's
 * static-mounted personas directory when it exists, falls back to a CSS
 * radial-gradient + initial placeholder when the pack has no portrait yet
 * (bundled personas without assets, user-created personas mid-generation).
 *
 * Backend mounts /personas at the health port (:8767) via StaticFiles, so
 * portrait URLs are absolute: http://localhost:8767/personas/<id>/avatar/portrait.png.
 */

"use client";

import { useState } from "react";

export interface PersonaPortraitProps {
  id: string;
  displayName: string;
  hue: number;
  size?: number;
  /** Subtle glow / scale when the card is being hovered upstream. */
  animated?: boolean;
}

const ASSETS_BASE =
  process.env.NEXT_PUBLIC_AETHER_ASSETS_BASE ?? "http://localhost:8767/personas";

export function PersonaPortrait({
  id,
  displayName,
  hue,
  size = 96,
  animated = false,
}: PersonaPortraitProps) {
  const initial = displayName.charAt(0).toUpperCase();
  const [imageFailed, setImageFailed] = useState(false);
  const portraitUrl = `${ASSETS_BASE}/${id}/avatar/portrait.png`;

  return (
    <div
      role="img"
      aria-label={imageFailed ? `${displayName} portrait placeholder` : `${displayName} portrait`}
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
      {!imageFailed && (
        // Real AI-generated portrait — absolute URL lets both dev-server
        // (:3000) and static export (file://) load from backend :8767.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={portraitUrl}
          alt={`${displayName} portrait`}
          width={size}
          height={size}
          className="absolute inset-0 w-full h-full object-cover"
          draggable={false}
          onError={() => setImageFailed(true)}
        />
      )}
      {imageFailed && (
        <span
          className="font-medium text-fg-primary/90 relative z-10"
          style={{ fontSize: size * 0.42, letterSpacing: "-0.04em" }}
        >
          {initial}
        </span>
      )}
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
