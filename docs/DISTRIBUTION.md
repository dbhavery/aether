# Aether — Distribution Playbook (v1.0.0-pre launch)

> Shipped 2026-04-18. This file tracks where Aether was announced, where it still needs to be announced, and the drafts for each channel. Paste-ready; Don posts manually where the channel doesn't allow automation.

---

## Channel status

| Channel | Status | Posted | Notes |
|---|---|---|---|
| GitHub Release | ✅ Shipped | 2026-04-18 | `v1.0.0-pre`, pre-release flag, targets `dev`. URL: https://github.com/dbhavery/aether/releases/tag/v1.0.0-pre |
| GitHub repo metadata | ✅ Shipped | 2026-04-18 | Description + homepage + 12 topics set. |
| Portfolio (dbhavery.dev) | ✅ Shipped | 2026-04-18 | Theatrical showcase on branch `feature/portfolio/cinematic-redesign` → merge + deploy. |
| LinkedIn | ✅ Shipped | 2026-04-18 | Auto-posted via morning-intel's LinkedInPoster. Draft in § 2 below. |
| Show HN | ⏸ Draft ready | — | Don to paste manually at https://news.ycombinator.com/submit (Tuesday/Wednesday morning ET for best visibility). Draft in § 3. |
| Reddit r/LocalLLaMA | ⏸ Draft ready | — | Don to paste manually. Mod rules: no "Show/Self" flair spam; "Resources" flair fits. Draft in § 4. |
| Reddit r/selfhosted | ⏸ Draft ready | — | Fits their "open-source self-hostable" bar. Draft in § 5. |
| Reddit r/privacy | ⏸ Draft ready | — | Privacy-first angle reads better here than the LLM angle. Draft in § 6. |
| Product Hunt | ⏸ Not drafted | — | Pre-packaged installer required before PH makes sense (they expect installable products). Defer to v1.0 final. |
| Hacker News mailing | n/a | — | Organic Show HN only. |
| Dev.to / Hashnode | ⏸ Not drafted | — | A longer-form "how I built a local-first AI companion" post post-launch, not on day one. |
| X / Twitter | ⏸ No automation | — | Don to post manually if desired. Thread draft in § 7. |
| Bluesky / Mastodon | ⏸ No automation | — | Copy from § 7. |

---

## 1 — Social preview + metadata (GitHub)

Already shipped this launch:

```
description: A desktop AI companion you actually own. Pick a face, a voice, a mind — they live on your machine. 12 personas, 100+ LLM providers via litellm, local voice, persistent memory, MIT.
homepage: https://dbhavery.dev
topics: ai-assistant, local-first, privacy, llm, voice-assistant, ollama, litellm, chromadb, desktop-app, python, open-source, personal-ai
```

TODO: upload a social preview image (GitHub → Settings → Social preview, 1280×640 PNG) using the three-persona stage from the portfolio. Export from the portfolio showcase once branch is deployed.

---

## 2 — LinkedIn (POSTED)

The content that went live via morning-intel's LinkedInPoster:

> The ergonomic gap in AI assistants right now isn't raw capability — it's ownership.
>
> Cloud assistants send every word to a server. They change personality every six weeks without asking. They charge per request and lock you into one model. They're rented, not owned.
>
> This week I shipped Aether — a desktop AI companion that's the opposite. Install it once, pick one of twelve personas, bring your own LLM key or stay fully local with Ollama, and it's yours. Conversations never leave your machine unless you told them to. Persistent memory, voice, and video all work offline. MIT-licensed. Free.
>
> If you're building AI into a personal workflow and privacy matters more to you than marginal reasoning quality, local-first with cloud fallback is the pattern worth studying. The stack I landed on: litellm as the provider router (100+ models), faster-whisper for local STT, Chatterbox Turbo for per-persona voice cloning, ChromaDB for hybrid BM25 + dense-vector memory. The latency budget lands under 500 ms on a single consumer GPU; cost per query is $0 local, whatever the provider charges in cloud mode, no middleman markup.
>
> v1.0.0-pre is a source install (packaged installer is the next milestone). Three fully-rendered personas ship today — Aurora, Caelum, Luma. Nine more slots open for community packs. The schema for authoring your own is a YAML file, a portrait, and a 20-second voice reference. That's the whole API.
>
> Seven months of work, open from today.
>
> github.com/dbhavery/aether
>
> The thing I'm most curious about: whether anyone ships a pack I didn't see coming.

---

## 3 — Show HN (draft, paste manually)

**Title:** `Show HN: Aether – A local-first desktop AI companion you actually own`

**URL:** `https://github.com/dbhavery/aether`

**Body:**

> Aether is a desktop AI companion I've been building for about seven months. Today I pushed it to public preview.
>
> The thesis: cloud assistants are rented, not owned. They change personality without asking, charge per request, and send every word you say through someone else's server. Aether flips that — install it once, pick a persona, bring your own LLM key (or stay fully local with Ollama), and it's yours.
>
> Design choices worth calling out:
>
> - **litellm as the only LLM layer.** One abstraction across Ollama, OpenAI, Anthropic, Google, Groq, OpenRouter — 100+ providers. No vendor coupling in the brain module.
> - **Push-to-talk, not wake-word.** Porcupine/Snowboy added latency, false wakes, and a constantly-on mic. Push-to-talk is 449 ms end-to-end and the microphone is actually off until you want it on.
> - **Per-persona voice cloning with Chatterbox Turbo.** Each persona pack ships a 20-second reference WAV. The persona's voice in TTS is cloned at runtime, not pre-baked.
> - **Hybrid memory.** ChromaDB with BM25 + dense-vector fusion. Per-persona collections so different characters don't see each other's memory.
> - **Secrets in the OS keyring.** Never plaintext on disk. `keyring` → Windows Credential Manager / macOS Keychain / Secret Service on Linux.
> - **Authoring new personas is a YAML file + a portrait + a 20s voice reference.** No code changes, no rebuilds — dropped into `personas/<id>/` and loaded on next boot.
>
> What's in v1.0: chat / voice / video modes, 3 fully-rendered personas + 9 slots ready for community packs, onboarding wizard, sandbox settings panel, persistent memory, LiveDorter-ready avatar pipeline.
>
> What's not in v1.0 (deferred to v2): tool use / agent workflows, vision, mobile client, barge-in, packaged macOS/Linux installers.
>
> Runs source-only right now; Windows 11 is primary. Python 3.13, Next.js 15, pywebview shell. Looking for feedback — especially from anyone who ships a custom persona pack.
>
> Repo: https://github.com/dbhavery/aether
> Release notes: https://github.com/dbhavery/aether/releases/tag/v1.0.0-pre

---

## 4 — Reddit r/LocalLLaMA (draft)

**Title:** `Aether — local-first AI companion, push-to-talk + persona voice cloning + litellm multi-provider, MIT [Release]`

**Flair:** `Resources`

**Body:**

> I just pushed v1.0.0-pre of Aether, an open-source desktop AI companion built around local-first LLMs with optional cloud fallback. Posting here because this subreddit is exactly the audience that cares about the tradeoffs.
>
> **Architecture:**
>
> - LLM layer is litellm, so Ollama / OpenAI / Anthropic / Google / Groq / OpenRouter all work through one interface. Router has FAST / MAIN / HEAVY tiers per provider so a `what time is it` goes to a 7B local and a `refactor this module` goes to Opus, without user intervention.
> - Voice in = faster-whisper (local). Voice out = Chatterbox Turbo with per-persona voice cloning from a 20s reference WAV. Push-to-talk, no wake-word.
> - Memory = ChromaDB with BM25 + dense-vector fusion, per-persona isolation.
> - Secrets = OS keyring via the `keyring` package. Never plaintext.
>
> **Numbers:** 449 ms cold query → spoken answer on consumer GPU with Ollama qwen2.5:7b as FAST tier. $0/query local. Single 8 GB VRAM card runs everything except video mode (video wants 12 GB+).
>
> **Personas:** three fully-rendered packs ship (Aurora, Caelum, Luma — AI-generated portraits + 4 state images + voice reference + hand-authored system prompts). Nine canonical slots open for community packs. Schema is plain YAML; loader scans `personas/` on boot.
>
> **What's not there yet:** tool use, vision, mobile. All planned for v2. Packaged installer coming; right now it's source install on Windows 11 primary.
>
> MIT. Feedback welcome, especially on the tier router and the memory-fusion weights if anyone has done this pattern at scale.
>
> https://github.com/dbhavery/aether

---

## 5 — Reddit r/selfhosted (draft)

**Title:** `Aether — self-hosted AI companion. Runs on your GPU, remembers your conversations, MIT-licensed [Release]`

**Body:**

> Shipped the public preview of Aether today — an AI assistant you install once and keep on your own machine. Posting here because the self-hosting crowd cares about the privacy + ownership angle more than the "shiny AI" angle.
>
> **What you run:** a Python backend (FastAPI + WebSocket) + a Next.js frontend. Talks to Ollama for fully-local LLM, or to any cloud provider via litellm when you want more horsepower.
>
> **What stays on your machine:** conversations, persona memory, voice clones, API keys. Keys in the OS keyring. Memory in a local ChromaDB. No telemetry unless you opt in, which is off by default.
>
> **What leaves your machine:** only traffic to whichever cloud LLM you configured yourself. Pick "Ollama only" in the wizard and literally nothing leaves.
>
> **Surface:** chat, push-to-talk voice, or animated video avatar. Twelve personas (three fully built, nine slots for community packs). MIT, free forever.
>
> Windows 11 primary; code runs on macOS/Linux but not yet packaged.
>
> https://github.com/dbhavery/aether

---

## 6 — Reddit r/privacy (draft)

**Title:** `Built a local-first AI assistant after getting tired of every prompt going through OpenAI — open-source, MIT`

**Body:**

> Quick share, not an ad: I got tired of every sentence I typed into an assistant becoming training data for someone else, so I built one that doesn't. Released it today as open-source.
>
> The guarantees it can actually make:
>
> - Secrets (API keys) live in the OS keyring. Never plaintext, never transmitted.
> - Conversations, memory, and voice clones stay on your machine. Stored in a local ChromaDB you own.
> - No telemetry by default. The wizard asks explicitly; off unless you opt in.
> - No cloud traffic unless *you* configured a cloud provider. Pick Ollama in setup and literally zero bytes leave.
> - MIT-licensed, so you can verify all of the above by reading the code.
>
> It does chat, voice, and video. Twelve personas you can choose from. Install is source-only for now (packaged installer coming).
>
> https://github.com/dbhavery/aether
>
> Feedback welcome on the threat model specifically — the full write-up is in `docs/LLM-PROVIDERS.md § 6` and `docs/PRODUCT-PLAN.md § 1`.

---

## 7 — X / Bluesky / Mastodon thread (draft)

**Thread, 5 posts:**

1. `Shipped Aether today. Desktop AI companion that runs on your machine. Open-source, MIT. 12 personas, voice + video, any LLM you want. github.com/dbhavery/aether`

2. `The thesis: cloud assistants are rented, not owned. They change personality every six weeks. They charge per request. Every word goes through someone else's server. Aether is the opposite. Install once. Your machine, your memory, your keys.`

3. `449 ms cold query → spoken answer on a single consumer GPU with Ollama. $0/query local. Bring your own key for frontier models — litellm routes 100+ providers through one interface.`

4. `Persona pack = YAML + a portrait + 20 seconds of voice reference. Dropped into personas/<id>/ and loaded on next boot. No code, no rebuild. Community packs welcome.`

5. `v1.0.0-pre is source install. Packaged installer next. docs/PRODUCT-PLAN.md has the roadmap. Issues welcome. github.com/dbhavery/aether`

---

## Metrics to track post-launch

- GitHub stars (week 1, week 4)
- Clone count from `gh api repos/dbhavery/aether/traffic/clones`
- Unique visitor count from `gh api repos/dbhavery/aether/traffic/views`
- Issues opened vs closed ratio (signal of engaged users)
- LinkedIn post reach (morning-intel analytics collector)
- Referrer split (HN vs Reddit vs LinkedIn — tells you where to put the second wave)

Check all of the above with `gh api repos/dbhavery/aether/traffic/{clones,views,popular/referrers}` after a week.
