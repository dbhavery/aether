# Aether Frontend

The product UI — a Next.js 15 + React 19 + TypeScript app that runs in two modes:

1. **Desktop mode** — bundled into the Aether Windows installer, loaded by pywebview in a native window. This is how users interact with Aether.
2. **Portfolio widget mode** — a subset of the UI deployed to `dbhavery.ai` as an inline text-chat demo, backed by the rate-limited Aether Guest LLM.

**Status:** Directory placeholder. Scaffolded in **P2 — Frontend scaffold** (see [../docs/PRODUCT-PLAN.md](../docs/PRODUCT-PLAN.md)).

---

## Target stack

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Framework | Next.js 15 (App Router) | Matches `dbhavery.ai` portfolio stack |
| UI | React 19 + TypeScript | Standard |
| Styling | Tailwind v4 | Fast, consistent |
| Component primitives | shadcn/ui (headless) | Accessible, themable |
| State (app-level) | Zustand | Simple, low-overhead |
| Server state | React Query | Caching, retries |
| WebSocket client | Native `WebSocket` wrapped in typed hook | No dep for something this simple |
| MJPEG rendering | `<img src="http://localhost:8770/stream">` inside a canvas for smoothing | Matches backend contract |
| Animation | Framer Motion | For mode transitions, wizard page changes |
| Routing | Next.js App Router | File-based |

---

## Directory structure (target — after P2)

```
frontend/
├── app/
│   ├── (shell)/              grouped routes with shared chrome
│   │   ├── chat/             text chat mode
│   │   ├── sandbox/          settings, persona switching, usage
│   │   └── video/            avatar + voice mode
│   ├── (onboarding)/
│   │   ├── 1-welcome/
│   │   ├── 2-avatar/
│   │   ├── 3-personality/
│   │   ├── 4-name/
│   │   ├── 5-llm/
│   │   ├── 6-voice/
│   │   ├── 7-terms/
│   │   └── 8-handoff/
│   ├── layout.tsx
│   ├── page.tsx              (routing gate: wizard or chat)
│   └── globals.css
├── components/
│   ├── chat/                 ChatBubble, ChatInput, StreamingMessage
│   ├── avatar/               AvatarView, IdleIndicator, StateBadge
│   ├── voice/                PushToTalkButton, AudioMeter, Transcript
│   ├── wizard/               step components, navigation
│   ├── settings/             form primitives for Sandbox
│   └── ui/                   shadcn primitives, theme tokens
├── lib/
│   ├── ws.ts                 typed WebSocket client (:8765)
│   ├── api.ts                REST client (:8766 if used)
│   ├── keyring.ts            bridge to pywebview JS-Python for key storage
│   ├── stores/               Zustand stores (session, persona, wizard, telemetry)
│   └── types.ts              event types mirrored from backend
├── design/
│   ├── tokens.css            colors, spacing, radii (CSS vars)
│   └── theme.tsx             provider + dark mode
├── public/
│   └── personas/             symlink or build-time copy of ../personas/*/avatar/portrait.png for wizard
├── next.config.ts
├── package.json
└── tsconfig.json
```

---

## Development

```bash
# One-time
cd frontend
npm install

# Dev mode (connects to backend on :8765)
npm run dev

# Build for desktop bundle
npm run build
npm run export  # → frontend/out/ static files

# Build for portfolio widget variant
npm run build:widget  # → frontend/out-widget/
```

---

## Design system notes

- **Dark theme only in v1.0.** Light mode is a post-launch consideration.
- **Fresh design, not `don-design-system`** (those tokens are locked-outdated per memory feedback 2026-03-22).
- **Typography:** follow portfolio (IBM Plex Sans for body, per portfolio deploy 2026-04-13).
- **Avatar view is the focal element** in Video mode — UI chrome recedes, avatar fills most of the frame.
- **Chat bubbles:** minimal, not skeuomorphic. Streaming responses show a subtle cursor/pulse.
- **Push-to-talk:** dominant button in Voice/Video mode, subtle indicator in Chat mode.

---

## Portfolio widget variant

A reduced build (`out-widget/`) containing:
- Chat mode only (no video, no voice).
- Hardcoded to Aether Guest provider.
- Capped to 10 turns per session (client-side + server-side).
- Heavy rate-limiting warning banner.
- "Try the full app →" CTA linking to download.

This is what embeds in `dbhavery.ai` as an iframe. Design intent: prove the shell, the conversation feel, and the streaming UX — without promising what the product can't deliver in a web iframe (no local voice, no local avatar).

---

## Testing

- **Unit:** Vitest for component logic.
- **Integration:** Playwright hitting the real backend.
- **Visual regression:** later — not v1.0.

---

## Pywebview integration

pywebview launches a native window pointing at `frontend/out/index.html`. Python-side functions are exposed via pywebview's `js_api` for things JS can't do:
- Native file dialogs.
- OS keyring read/write.
- Native audio device enumeration.
- Taskbar icon state.

All such bridges live in `desktop/bridge.py` (Python) and `frontend/lib/keyring.ts` (JS wrappers).
