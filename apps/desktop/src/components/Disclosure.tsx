import { useState } from "react";

const DISCLOSURE_VERSION = "v0-2026-04-19";
const STORAGE_KEY = "aether.disclosure.acknowledged";

/**
 * One-time first-run banner. Plain-language local-first statement per
 * docs/ONBOARDING-SPEC.md (Step 1). Dismisses into a small help icon
 * once acknowledged; re-accessible from the header.
 */
export function Disclosure({
  forceOpen,
  onClose,
}: {
  forceOpen?: boolean;
  onClose?: () => void;
}) {
  const stored = typeof window !== "undefined"
    ? window.localStorage.getItem(STORAGE_KEY)
    : null;
  const [open, setOpen] = useState(forceOpen || stored !== DISCLOSURE_VERSION);

  if (!open) return null;

  const accept = () => {
    try {
      window.localStorage.setItem(STORAGE_KEY, DISCLOSURE_VERSION);
    } catch {
      // ignore — worst case the banner shows next launch too
    }
    setOpen(false);
    onClose?.();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="disclosure-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fadeIn"
    >
      <div className="neu-raised mx-6 max-w-lg rounded-xl p-7">
        <h2
          id="disclosure-title"
          className="text-base font-medium tracking-tight text-aether-text"
        >
          Welcome to Companion
        </h2>
        <p className="mt-3 text-[13px] leading-relaxed text-aether-muted">
          Companion is a local-first, desktop-native AI companion. This is an
          early preview — quiet, minimal, and under your control.
        </p>
        <ul className="mt-4 space-y-2 text-[12.5px] text-aether-muted">
          <li className="flex gap-2">
            <span className="text-aether-ok">•</span>
            <span>
              <strong className="text-aether-text">Stays on your machine.</strong>{" "}
              Memory and persona state live here. Nothing leaves unless you
              explicitly enable a remote provider.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-aether-ok">•</span>
            <span>
              <strong className="text-aether-text">Remembers this session.</strong>{" "}
              Short-horizon conversation continuity only. Durable memory comes
              in a later slice and will be fully editable.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-aether-ok">•</span>
            <span>
              <strong className="text-aether-text">Asks before doing anything risky.</strong>{" "}
              Actions that touch files, tools, or other sensitive surfaces
              surface an approval prompt first.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="text-aether-warn">•</span>
            <span>
              <strong className="text-aether-text">Preview.</strong> Expect rough
              edges. No avatar yet. No voice yet. No durable memory yet.
            </span>
          </li>
        </ul>
        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={accept}
            className="rounded-md border border-aether-borderHi bg-aether-elevated px-4 py-2 text-[13px] text-aether-text hover:border-aether-text transition-colors"
          >
            I understand — let's start
          </button>
        </div>
      </div>
    </div>
  );
}
