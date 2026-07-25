#!/usr/bin/env node
// Aether L5 — Playwright driver subprocess.
//
// Long-lived Node process spawned by `PlaywrightExecutor` in the
// `aether-l5-browser` Rust crate. Reads JSON-lines requests on stdin,
// writes JSON-lines replies on stdout. One reply per request, keyed by
// the caller-supplied `req_id`.
//
// Wire format (one JSON object per line, both directions):
//
//   request:  {"req_id": <int>, "op": <string>, "args": {...}}
//   ok reply: {"req_id": <int>, "ok": <op-specific-value>}
//   err reply:{"req_id": <int>, "err": "<message>", "kind": "<variant>"}
//
// Supported `op` values match the BrowserExecutor trait verbs:
//   open, navigate, read_page, extract, fill_form, submit, close.
//
// Error `kind` strings (must stay in sync with `error_from_kind` in
// playwright_stub.rs):
//   Navigation, SelectorNotFound, SessionNotFound, Timeout, Internal.
//
// Sessions are tracked in a Map<sessionId, {browser, context, page}>.
// Each `open` call creates a fresh BrowserContext (isolated cookies,
// localStorage) so concurrent sessions don't bleed state.
//
// SIGTERM / SIGINT triggers graceful shutdown — every live context is
// closed before the process exits.

import { createInterface } from "node:readline";
import { randomUUID } from "node:crypto";

// --- Lazy playwright import ----------------------------------------
//
// We import playwright dynamically so a misconfigured workspace
// (playwright not installed) surfaces a structured error to the Rust
// side instead of crashing on first import.
let chromium = null;
let playwrightImportError = null;
try {
  const pw = await import("playwright");
  chromium = pw.chromium;
} catch (e) {
  playwrightImportError = e;
}

// sessionId -> { browser, context, page }
const sessions = new Map();

function reply(req_id, ok) {
  process.stdout.write(JSON.stringify({ req_id, ok }) + "\n");
}

function replyErr(req_id, err, kind = "Internal") {
  const message = err && err.message ? err.message : String(err);
  process.stdout.write(
    JSON.stringify({ req_id, err: message, kind }) + "\n",
  );
}

function classifyError(e) {
  // Heuristics for mapping Playwright errors back to typed Rust
  // variants. Playwright doesn't expose stable error subclasses, so we
  // sniff the message.
  const msg = (e && e.message) || String(e);
  if (/timeout/i.test(msg)) return "Timeout";
  if (/no element|selector .* did not|locator .* did not/i.test(msg))
    return "SelectorNotFound";
  if (/net::|err_/i.test(msg)) return "Navigation";
  return "Internal";
}

function getSession(sessionId) {
  const s = sessions.get(sessionId);
  if (!s) {
    const e = new Error(`session not found: ${sessionId}`);
    e._kind = "SessionNotFound";
    throw e;
  }
  return s;
}

// --- Op handlers ----------------------------------------------------

async function opOpen(args) {
  if (!chromium) {
    throw Object.assign(
      new Error(
        `playwright not installed in this workspace: ${
          playwrightImportError && playwrightImportError.message
        }`,
      ),
      { _kind: "Internal" },
    );
  }
  const url = args.url;
  if (typeof url !== "string") {
    throw Object.assign(new Error("missing args.url"), {
      _kind: "Internal",
    });
  }
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto(url, { waitUntil: "domcontentloaded" });
  } catch (e) {
    await browser.close().catch(() => {});
    throw Object.assign(e, { _kind: "Navigation" });
  }
  const sessionId = randomUUID();
  sessions.set(sessionId, { browser, context, page });
  return sessionId;
}

async function opNavigate(args) {
  const session = getSession(args.session);
  try {
    await session.page.goto(args.url, { waitUntil: "domcontentloaded" });
  } catch (e) {
    throw Object.assign(e, { _kind: "Navigation" });
  }
  return null;
}

async function opReadPage(args) {
  const session = getSession(args.session);
  const page = session.page;
  const url = page.url();
  const title = await page.title();
  const text_content = await page.evaluate(() => document.body.innerText);
  return {
    url,
    title,
    text_content,
    captured_at_ms: Date.now(),
  };
}

async function opExtract(args) {
  const session = getSession(args.session);
  const selector = args.selector;
  const locator = session.page.locator(selector);
  const count = await locator.count();
  if (count === 0) {
    throw Object.assign(new Error(`selector matched 0 elements: ${selector}`), {
      _kind: "SelectorNotFound",
    });
  }
  const out = [];
  for (let i = 0; i < count; i++) {
    out.push(await locator.nth(i).innerText());
  }
  return out;
}

async function opFillForm(args) {
  const session = getSession(args.session);
  const fields = args.fields || [];
  for (const f of fields) {
    try {
      await session.page.fill(f.selector, f.value);
    } catch (e) {
      throw Object.assign(e, { _kind: classifyError(e) });
    }
  }
  return null;
}

async function opSubmit(args) {
  const session = getSession(args.session);
  try {
    await session.page.click(args.selector);
  } catch (e) {
    throw Object.assign(e, { _kind: classifyError(e) });
  }
  return null;
}

async function opClose(args) {
  const session = sessions.get(args.session);
  if (!session) {
    // Idempotent close — never error on missing session.
    return null;
  }
  sessions.delete(args.session);
  await session.browser.close().catch(() => {});
  return null;
}

const HANDLERS = {
  open: opOpen,
  navigate: opNavigate,
  read_page: opReadPage,
  extract: opExtract,
  fill_form: opFillForm,
  submit: opSubmit,
  close: opClose,
};

// --- Main loop ------------------------------------------------------

const rl = createInterface({ input: process.stdin });

rl.on("line", async (line) => {
  if (!line.trim()) return;
  let req;
  try {
    req = JSON.parse(line);
  } catch (e) {
    // No req_id on a malformed line — log to stderr and drop.
    process.stderr.write(`[driver] bad JSON: ${e.message}\n`);
    return;
  }
  const { req_id, op, args } = req;
  const handler = HANDLERS[op];
  if (!handler) {
    replyErr(req_id, `unknown op: ${op}`, "Internal");
    return;
  }
  try {
    const result = await handler(args || {});
    reply(req_id, result);
  } catch (e) {
    const kind = e && e._kind ? e._kind : classifyError(e);
    replyErr(req_id, e, kind);
  }
});

// --- Graceful shutdown ----------------------------------------------

async function shutdown(reason) {
  process.stderr.write(`[driver] shutting down: ${reason}\n`);
  const closes = [];
  for (const [, s] of sessions) {
    closes.push(s.browser.close().catch(() => {}));
  }
  await Promise.allSettled(closes);
  process.exit(0);
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
process.stdin.on("end", () => shutdown("stdin closed"));
