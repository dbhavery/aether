# Drag-Drop File/Image Attachment — UX Research for Companion

> **Researched:** 2026-05-01
> **For:** Don (decision input — not a spec, not a plan)
> **Audience:** Companion (Tauri desktop chat surface, dark/minimal, single-window, L5-policy-gated)
> **Status quo:** Companion has zero drag-drop / file-attach / paste-image affordances today. Confirmed by `grep -rn "onDrop\|onDragOver\|onPaste\|FileReader" apps/desktop/src` returning zero hits.

---

## TL;DR

The 2026 dominant pattern across every modern chat surface is **whole-window drop overlay + composer-anchored chip strip + paste-to-inline-attach**. ChatGPT, Claude, Gemini, Perplexity, Slack, Discord, Linear, Cursor all do some version of this; differences are cosmetic.

For Companion, recommendation is **Perplexity-class compact** — paperclip in composer, whole-window drop with a centered overlay that **previews the L5 policy ask** ("Drop to attach — will request FilesRead permission on this path"), and a tight chip row above the composer that collapses to zero height when empty.

The Tauri-specific architecture call is the one that bites: must use `onDragDropEvent` (real file paths, what L5 needs) — not HTML5 `drop` (only blobs, breaks the path allowlist).

Six open questions belong to Don, not to me — clipboard-paste policy, drop-vs-send approval timing, allowlist-scope shape, overlay copy tone, `MediaUpload` capability scope, and modal-open-during-drop behavior.

---

## 1. Per-surface field notes

### Group A — AI chat (closest analogues)

**ChatGPT (web + desktop).** Whole-window drop zone — drag anywhere, surface dims with a centered "Drop to attach" overlay. Paste inline-attaches (Cmd/Ctrl+V). Attachments render as small chips above the composer text — image chips show thumbnail, file chips show icon + filename. Multi-file (10+). Removal: hover → small X top-right of chip. The "+" button on the composer left opens a dock with Files / Photos / Connectors. No file-type rejection at boundary; server validates. 512 MB/file (Plus). https://chatgpt.com

**Claude.ai.** Composer-anchored drop zone is the visual target, but actually accepts drops anywhere in the chat pane. Paste works inline. Chips appear inside the composer (above the text input, below the attachment bar). X on hover. Multi-file (up to ~5 visible chips, more collapse). Project Files surface is a separate persistent panel — distinct from per-message attachments. 30 MB/file. https://support.claude.com/en/articles/8241126-upload-files-to-claude

**Gemini / AI Studio.** Composer-anchored "+ Add" button. Drop overlay covers the chat. Chips render in a strip directly above composer; rounded corners, image thumb left, name right, X right. AI Studio additionally exposes a parts-list (multimodal-aware) — distinguishing inline parts from referenced files. https://aistudio.google.com

**Perplexity.** Minimal: a paperclip icon in the composer. Whole-window drop with dim overlay. Chips inline in composer, single row. Designed to disappear when nothing attached — zero clutter at rest. Closest aesthetic match to Don's "no clutter" instinct.

**Cursor.** Drag-drop into chat works; clipboard paste is buggy on Windows — known focus-routing bug where paste targets the open editor instead of the chat input (March 2026, still open). Chips in the composer with X. **Lesson:** focus-state must be explicit and visible, otherwise paste lands in the wrong surface and silently destroys user trust. https://forum.cursor.com/t/agent-chat-clipboard-image-paste-ctrl-v-context-menu-does-not-work-drag-and-drop-file-works/156818

### Group B — AI image / creator

**Krea.** Canvas-style. Multi-slot reference UI: separate dedicated zones for "Style", "Content", "Edit". Each slot is a labeled drop target with its own thumbnail. Slots have weight sliders. Annotation mode lets users mark up regions with per-region prompts. Gold standard for *role-distinguished* attachments — but heavy UI, not chat-shaped. https://www.krea.ai/blog/annotations

**Magnific.** Single hero drop zone on landing — full-bleed, dotted border, "Drop image or click to upload". One-shot. Minimal because the tool only does one thing.

**Midjourney web.** "+" opens a tray, image goes in `--iref`, `--sref`, or moodboard slot. Each slot explicit and named. Image weight adjustable per slot. https://chasejarvis.com/blog/how-to-control-midjourney-style-references-image-references-and-moodboards/

**ComfyUI.** Drop directly onto a Load Image node. Each node = one slot. Powerful but engineering-grade UI.

**Adobe Firefly.** Composer + reference-image side-panel. Reference is opt-in via a labeled card, never inline with the prompt. Distinct from the prompt zone — clear role separation.

### Group C — Creator dashboards

**Linear.** Paste inline-attaches in issues/comments. Drag-drop on the description field. Attachments render as cards below the description. Discreet, no chrome at rest.

**Notion.** Universal drag-drop creates *blocks*. Paste creates an image block. Block-based, not chip-based — different paradigm; only relevant as a counter-example for chat surfaces. https://www.notion.com/help/images-files-and-media

**Figma/FigJam.** Paste places at cursor. Drop places where dropped. Canvas surface — irrelevant pattern for transcript+composer.

**Slack/Discord.** Whole-channel drop with dim overlay. Paste inline. Strip above composer with thumbnail + filename + X. Multi-file queue. The composer turns into "affordance soup": paperclip + emoji + GIF + slash + workflow + … — clear "what to skip" example.

---

## 2. Cross-cutting findings

**Q: Dominant pattern in 2026?** Whole-window drop overlay + composer-anchored chip strip + paste-to-inline-attach. Universal.

**Q: AI chat convergence?**
- Single, undifferentiated attachment role (just "context"). No reference-vs-edit distinction.
- Chips inside or just above the composer.
- Paperclip / "+" left of input.
- Whole-window drop with dim overlay.
- Per-chip X removal on hover.

**Q: Where they diverge usefully?** Creator tools (Krea, Midjourney, Firefly) split attachments into named roles (style / content / edit / mask). Chat surfaces flatten to one role. Companion is chat-first today, so flat is correct now — but the role distinction matters once Companion has tool-using agents that *act on* a file vs. *read context from* it.

**Q: Best compact pattern for single-composer chat?** Perplexity's. Paperclip in composer + whole-window drop overlay + tight chip row that collapses to nothing when empty. No persistent dock, no asset tray, no project-files panel.

**Q: Worst pattern?**
- Slack-style "affordance soup" composer with 6+ icons.
- Notion's block-paradigm (wrong mental model for a chat composer).
- Cursor's focus bug (ambiguous focus state means paste lands in the wrong surface and silently destroys user trust).

**Q: Tauri-specific gotchas?** See §3.

---

## 3. Tauri implementation notes

**The single biggest decision: Tauri intercepts file drops by default.** When `dragDropEnabled` is true (default), the OS-level drop event is captured by Tauri's native handler and the HTML5 `drop` event in the webview never fires. You also do *not* get the file *contents*, only paths.

Two viable architectures:

**A. Tauri-native events — recommended for Companion.**
- Keep `dragDropEnabled: true` in `tauri.conf.json`.
- Listen via `getCurrentWebview().onDragDropEvent()` — fires for `enter`, `over`, `drop`, `leave` with file paths.
- You get **real file paths**, which is what L5 needs to issue a `FilesRead` capability check against the path allowlist.
- Trade-off: known limitation — webview doesn't get mouse position during drag on some platforms, so element-scoped drop zones require a mouse-tracking workaround (mouseenter/mouseleave on the target element + filter Tauri drop events by hover state). Acknowledged by the Tauri team.
- Drop position is inaccurate when devtools is open — debugging caveat, not a prod issue.
- API was renamed `FileDropEvent` → `DragDropEvent` in 2.0; `fileDropEnabled` → `dragDropEnabled`. https://v2.tauri.app/reference/javascript/api/namespacewebview/

**B. Browser-native HTML5 drop.**
- Set `dragDropEnabled: false` in window config.
- Standard `dragover` / `drop` listeners; must call `event.preventDefault()` on `dragover` to stop the webview navigating to the file.
- You get **file contents (Blobs)** but **not paths** — security-by-design in browsers.
- Bad for L5: without a path, you can't issue a `FilesRead` capability check on the actual filesystem location. You'd be promoting an unbound blob into the agent's context with no allowlist enforcement.

**Verdict for Companion: Architecture A.** L5's path-based allowlist requires real paths. https://github.com/tauri-apps/tauri/discussions/9696

**Other Tauri specifics:**
- Clipboard image paste (Cmd/Ctrl+V on a screenshot) goes through the webview's normal clipboard API — `navigator.clipboard.read()` returns blobs. No path. Same L5 concern: a pasted screenshot is a blob with no filesystem origin. This needs a different policy treatment from a dropped file (see open question 1).
- `tauri-plugin-fs` gates filesystem access via the capability system — wire `FilesRead` checks here, not in the UI layer.
- `tauri-plugin-drag` is for the *outbound* direction (drag *out* of Companion to the OS). Not needed for inbound attachment.

---

## 4. Recommendation for Companion

**Adopt the Perplexity-class compact pattern, gated by L5.**

### UX sketch

```
+---------------------------------------------------------------+
|  Transcript                                                   |
|  ...                                                          |
|  [ assistant message ]                                        |
|  [ user message ]                                             |
|                                                               |
+---------------------------------------------------------------+
|  [thumb 64x64 X]  [thumb 64x64 X]   <-- chip row, only when   |
|                                         attachments present   |
+---------------------------------------------------------------+
|  [+]  Type a message…                              [Send] >   |
+---------------------------------------------------------------+

While dragging a file over the window:
+---------------------------------------------------------------+
|                                                               |
|              ╭─────────────────────────────╮                  |
|              │   Drop file to attach       │  <-- centered    |
|              │   (will request FilesRead)  │      overlay,    |
|              ╰─────────────────────────────╯      80% dim     |
|                                                               |
+---------------------------------------------------------------+
```

### Concrete behaviors

1. **Drop targets:** whole-window drop. Use Tauri's `onDragDropEvent`. On `enter`, fade in a centered modal-style overlay with copy that explicitly previews the policy ask: "Drop to attach — will request FilesRead permission on this path." This is unique to Companion and turns a generic drop into a policy-aware one.
2. **Paste:** Cmd/Ctrl+V on a clipboard image creates a chip with `source: clipboard` (no path). Treat differently — see open question 1.
3. **Chip row:** appears above composer only when ≥1 attachment exists. Collapses to zero height otherwise. 64×64 thumb for images, icon+filename for non-images. X on hover, top-right corner. Keyboard: focus chip + Backspace removes.
4. **Composer button:** single `+` (or paperclip — pick one and stick) on the left. Opens an OS file picker via `tauri-plugin-dialog`. No expanding dock. No emoji/GIF/etc.
5. **Multi-file:** support up to N (suggest 8). Beyond N, show "+3 more" overflow chip.
6. **File-type discipline:** reject non-allowlisted types at the boundary with a toast — don't let them sit in the chip row only to fail at send. Allowlist driven by L5 policy, not hardcoded.
7. **Approval integration:** dropping a file is implicitly a `FilesRead` request. The drop overlay copy previews it; the actual approval lands when the message is sent or when the chip is committed (TBD — open question 2). Reuse the Wave 14 ApprovalModal — show one modal per send, batched across all attachments, with the radio (allow once / allow always for path / deny).
8. **Progress / errors:** for local files there's no upload — only a hash + read. Show a thin progress line on the chip during read for files >5 MB. On error (denied capability, file gone), the chip turns red with a tooltip; click to retry or remove.
9. **Reference-image roles:** **skip for now.** Companion is chat-first, single-role context. Adding Krea-style slot UI is premature. When Companion gets edit/generate tools, add a per-chip role chip (`context` / `edit` / `style`) — don't add separate drop zones.

### What to skip explicitly

- No persistent file panel (Claude Projects style). Companion has no project surface yet.
- No dock-style "+" with Files/Photos/Connectors expansion. Single button.
- No emoji/GIF/slash buttons in the composer.
- No drag-drop reordering of chips (low value, high cost).
- No inline image rendering inside the composer text — chips above only.
- No HTML5-drop architecture (would break L5 path allowlist).

---

## 5. Open questions for Don

1. **Clipboard-pasted images have no filesystem path.** What policy applies? Options: (a) auto-allow as ephemeral blobs (no `FilesRead` because there's no file to read), (b) require a new `MediaUpload` capability that gates *any* media into transcript context, (c) write blob to a Companion-managed temp dir and treat as a normal `FilesRead` against that path. Option (c) is cleanest for audit trail; option (b) is cleanest for policy clarity. **Lean: (b) + (c) layered** — write to temp, gate the temp-write under `MediaUpload`, gate the read under `FilesRead` on the temp path with auto-allow for the Companion temp dir.

2. **When does the approval fire — on drop or on send?** Drop = early friction, but user can adjust before send. Send = batched, less interruptive, but the chip is in a "pending approval" state pre-send. **Lean: on send, batched** — one approval modal listing every attachment + path, single accept/deny.

3. **Allowlist scope for "always allow":** path? parent directory? extension? The Wave 13 allowlist plumbing is path-based today — drop UX should match it. If allowlist is path-only, "allow always" on a screenshot is useless because the path is `C:\Users\dbhav\Pictures\Screenshots\<timestamp>.png` and never repeats. Consider parent-dir allowlist for media folders.

4. **Policy preview copy.** The drop overlay copy "will request FilesRead" is a strong UX choice — it makes the policy visible at the gesture, not after. Confirm this matches Companion's broader approval-language style or feels too system-y.

5. **`MediaUpload` capability scope.** Is it a new L5 capability or a flag on `FilesRead`? If new, what's its surface — does it apply to TTS audio, persona reference images, etc. as well? Worth scoping before UI lands.

6. **Drop overlay during ApprovalModal-open state.** If the approval modal is open and the user drops another file, what happens? Suggest: ignore drops while modal is open, or queue them.

---

## Sources

- https://v2.tauri.app/reference/javascript/api/namespacewebview/
- https://v2.tauri.app/blog/tauri-20/
- https://github.com/tauri-apps/tauri/discussions/9696
- https://github.com/tauri-apps/tauri/discussions/4736
- https://support.claude.com/en/articles/8241126-upload-files-to-claude
- https://www.notion.com/help/images-files-and-media
- https://www.krea.ai/blog/annotations
- https://docs.krea.ai/user-guide/features/krea-image
- https://chasejarvis.com/blog/how-to-control-midjourney-style-references-image-references-and-moodboards/
- https://forum.cursor.com/t/agent-chat-clipboard-image-paste-ctrl-v-context-menu-does-not-work-drag-and-drop-file-works/156818
- https://forum.cursor.com/t/bug-pasting-an-image-in-chat-inserts-it-into-the-open-markdown-file-instead-chat-input-appears-focusedbug/155745
- https://cursor.com/changelog
- https://api.slack.com/reference/messaging/attachments
