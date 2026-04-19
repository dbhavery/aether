# 04 — User-Facing Modes

The product surfaces the user can interact through. Three primary modes plus one clarification.

---

## 1. Chat / Text mode

### Role
The primary core interaction mode. The product's default.

### Capabilities
- Text input and output
- Optional microphone input (push-to-talk or VAD)
- Optional voice output
- Can operate fully text-only
- Basic state feedback (listening / thinking / replying) even without the avatar

### Behavior rules
- Must remain fully useful when the avatar is disabled or unavailable.
- The assistant muting controls (user mute / assistant mute) are per-direction, not per-mode.
- Responsiveness and interaction clarity outrank answer depth at this surface.

### Why chat is primary
- Best mode for precision and fast work.
- Lowest friction.
- Never gated behind avatar rendering performance.
- Works on weakest hardware tiers with graceful degradation.

---

## 2. Sandbox / Settings / Customization mode

### Role
The product's **control center** — the configuration surface Don (or any user) uses to shape the assistant.

### Core responsibilities
- **Persona customization** — identity, tone, style, voice, appearance
- **Model selection** — per-tier, per-task; local vs remote preferences
- **Memory controls** — view, edit, revoke, delete, export, retention rules
- **Permission controls** — presets, granular capability matrix, resource scopes, approvals, logs
- **Hardware / performance settings** — tier selection, VRAM budget, model pack management
- **Integrations** — browser, email, tools (per permissions)
- **Trust center** — action history, disclosures, what the assistant can/cannot do
- **Advanced / builder controls** — for power users; hidden behind explicit expansion

### Design tone
Calm, precise, legible. Not cinematic. Every control has an (i) info explainer.

---

## 3. Video / Avatar mode

### Role
Face-to-face conversational mode. User sees the avatar assistant in a live video-call-like interaction.

### Core experience
- Avatar **speaks, listens, responds, animates** in real time
- Looks and feels like a FaceTime-style session with a human presence
- Never freezes unnaturally — always shows *some* social state (listening / thinking / acknowledging)

### Avatar behaviors
- Lip-sync
- Facial animation (state-linked + speech-linked expressions)
- Eye behavior (gaze, blink, micro-saccades)
- Listening posture
- Speaking behavior
- Thinking / acknowledgement behavior (distinct from speaking)
- **Later (flagship milestone):** hand and body movement, full-body

### Degradation
Must degrade gracefully to simpler avatar levels on weaker hardware:
- **Lite:** headshot, basic lip-sync, limited facial animation, simpler gaze logic
- **Balanced:** improved facial animation, gaze + blink, listening/thinking states distinct
- **Full / Pro:** richer facial animation, idle motion, eventually gesture/body

### Muted visual mode
User can keep the avatar visible without voice playback, or keep the avatar present but minimized. Voice output is per-direction, not coupled to avatar rendering.

---

## 4. Voice-only — clarification (not a separate mode)

### What voice-only actually is
Voice-only is **chat/text mode with microphone and optional voice output enabled** — not a separate product mode.

Either party may be muted visually or aurally:
- User can mute mic (type input only)
- Assistant can mute voice output (text responses only)
- Avatar can be hidden (voice + text with no visual)
- Everything can be visible and audible (full mode)

### Why this matters
- **One orchestration path** — voice-only reuses the full chat pipeline. No duplicate state machines.
- **One permissions model** — mic/audio access is a scoped capability, not a mode switch.
- **One user mental model** — "I'm talking to my assistant," not "I'm in voice mode now."

### Configuration surfaces
- Mic on/off toggle
- Voice output on/off toggle
- Avatar visibility toggle (on / minimized / off)
- Push-to-talk vs VAD turn detection preference

---

## Mode interaction matrix

| Surface | Text chat | Voice in | Voice out | Avatar visible |
|---------|-----------|----------|-----------|----------------|
| Chat mode (default) | ✓ | optional | optional | ✗ |
| Chat + voice in | ✓ | ✓ | optional | ✗ |
| Chat + avatar | ✓ | optional | optional | ✓ |
| Full avatar mode | optional | ✓ | ✓ | ✓ |
| Muted visual | ✗ | ✓ | ✓ | ✓ |
| Text + avatar silent | ✓ | ✗ | ✗ | ✓ |

All combinations are valid. The UI does not gate them behind artificial "mode" switches — they are toggle combinations.

---

## Mode-specific UX tone

| Mode | Tone |
|------|------|
| Chat | Calm, fast, precise |
| Settings / Sandbox | Calm, legible, controlled |
| Avatar | Cinematic, emotionally alive, socially present |
| Trust center (inside settings) | Transparent, reassuring, concrete |

---

## Cross-references
- UX principles: [05_ux_principles.md](05_ux_principles.md)
- Architecture (per-mode data flow): [08_system_architecture.md](08_system_architecture.md)
- Avatar subsystem: [11_avatar_presence.md](11_avatar_presence.md)
- Permissions (mic/audio/camera scopes): [12_permissions_autonomy.md](12_permissions_autonomy.md)
