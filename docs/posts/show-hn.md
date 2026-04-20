# Show HN — draft

**Title:**
Show HN: Aether – local-first AI companion architecture with a non-bypassable policy gate (Rust)

**URL field:**
https://github.com/dbhavery/aether

**Text field:**

Aether is an architecture for a long-lived local AI companion. It is preview-grade, MIT-licensed, and doesn't ship a runnable product yet. What it does ship is the spine: a seven-layer Rust workspace where every side-effectful call routes through one non-bypassable policy engine.

The thing I want feedback on is the policy engine itself. Decisions are typed values, not booleans (`Allow / Ask / DraftOnly / Deny / NeedsUpgrade`), every decision writes a sealed audit row before returning, and the audit log is a SHA-256 hash chain with HMAC-SHA256 signatures over each row. Tampering with the DB file breaks `verify_chain` in a specific, named way. Eight enumerated triggers force re-evaluation of persistent grants. The layer-boundary linter runs in CI and refuses any sibling-engine import that would let one layer reach around the gate.

The demo is a tiny CLI in `apps/l1-cli/`. `cargo run -p aether-l1-cli`, then try `read /tmp/x`, `shell ls`, `delete /tmp/y`. Each command exercises a different decision branch and prints the policy/audit trail.

What's not in the preview: real LLM calls, desktop shell, STT/TTS, persistent memory across sessions. Those are the next six sessions on the roadmap. Right now it's the architecture you'd review before wiring any of that in.

Writeup on why the policy gate is load-bearing: [blog post URL]
Architecture doc: https://github.com/dbhavery/aether/blob/dev/ARCHITECTURE.md

Happy to argue about any of it.

---

## Submission notes (for Don, not for HN)

- **Timing:** Tuesday–Thursday, 7–9 AM Pacific is the honest sweet spot for Show HN. Don't submit Friday afternoon or weekends.
- **Title rules:** HN strips "Show HN:" prefix on display but requires it in the title. Under 80 chars. No marketing adjectives; HN moderators will rewrite them.
- **URL:** Link directly to the GitHub repo, not the landing page. HN voters trust repo URLs more.
- **First comment:** Post one comment from your own account, as the author, with the technical detail you want discussed first. Recommended: the five `Decision` variants + the five-stage evaluator. Don't post a list of features.
- **Don't engage with dismissive comments for 30 minutes.** The first thirty minutes decide whether it lands. Reply to substantive critique only.
- **Prepared replies you will get:**
  - *"Why not just use LangChain?"* → Short answer: LangChain is a runtime chain-composer; Aether is a layered architecture with a non-bypassable policy engine. Different thing. Longer answer in the blog post.
  - *"Why Rust?"* → Long-lived process, tight memory story, strong type system for the `Capability` enum, and the audit path is where you want sub-millisecond p95. Rust buys all of those.
  - *"It's not usable yet."* → Agreed. The tag is `v0.1.0-oss-preview.0` and the README says so in plain language. The question is whether the architecture is worth the review now, or when there's a desktop shell.
  - *"Hash chains aren't novel."* → Correct. The point isn't novelty. The point is that a local-first companion needs tamper-evident audit as *ground-floor*, not as an optional middleware, and almost nothing in the current AI-agent space actually builds that way.

- **If it lands:** Enable GitHub Discussions in the repo settings before the post. You'll get questions that don't fit an issue tracker.

- **If it doesn't land:** Lobsters accepts Rust + AI-architecture posts. Try there with the same body, 24 hours later, under the `rust` and `practices` tags. And `/r/rust` and `/r/LocalLLaMA` both accept architecture writeups if the code is linked.
