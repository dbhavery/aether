/*
 * Aether Customer Assistant — embeddable chat widget.
 *
 * Drop-in usage on any company site:
 *   <script
 *     src="http://localhost:8200/widget.js"
 *     data-company="northwind-outdoors"
 *     data-api="http://localhost:8200"
 *     defer></script>
 *
 * The widget reads its company id + API base from the <script> tag's data-*
 * attributes, fetches branding from /companies/{id}/branding to theme itself,
 * and talks to POST /chat. Everything lives inside a Shadow DOM so the host
 * page's CSS can't leak in and the widget's CSS can't leak out.
 */
(function () {
  "use strict";

  // ── Locate this script tag + read config ────────────────────────────────
  var current =
    document.currentScript ||
    (function () {
      var all = document.getElementsByTagName("script");
      return all[all.length - 1];
    })();

  var COMPANY = (current && current.getAttribute("data-company")) || "demo";
  var API = (current && current.getAttribute("data-api")) || "";
  API = API.replace(/\/$/, "");

  var DEFAULT_COLORS = {
    primary: "#2563eb",
    accent: "#f59e0b",
    background: "#0f1115",
    surface: "#171a21",
    text: "#e8eaed",
  };

  // ── Build the host element + shadow root ─────────────────────────────────
  var host = document.createElement("div");
  host.setAttribute("data-aether-customer-assistant", COMPANY);
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });

  function styleBlock(colors) {
    return (
      "" +
      ":host{all:initial}" +
      "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}" +
      ".launcher{position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;border:none;cursor:pointer;" +
      "background:" + colors.primary + ";color:#fff;font-size:26px;box-shadow:0 6px 20px rgba(0,0,0,.35);z-index:2147483000}" +
      ".launcher:hover{filter:brightness(1.08)}" +
      ".panel{position:fixed;bottom:92px;right:20px;width:370px;max-width:calc(100vw - 40px);height:520px;max-height:calc(100vh - 120px);" +
      "display:none;flex-direction:column;border-radius:16px;overflow:hidden;z-index:2147483000;" +
      "background:" + colors.background + ";color:" + colors.text + ";box-shadow:0 16px 48px rgba(0,0,0,.5)}" +
      ".panel.open{display:flex}" +
      ".header{padding:14px 16px;background:" + colors.primary + ";color:#fff}" +
      ".header h3{margin:0;font-size:15px;font-weight:600}" +
      ".header p{margin:2px 0 0;font-size:12px;opacity:.85}" +
      ".log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}" +
      ".msg{max-width:85%;padding:9px 12px;border-radius:12px;font-size:13.5px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}" +
      ".msg.user{align-self:flex-end;background:" + colors.primary + ";color:#fff;border-bottom-right-radius:3px}" +
      ".msg.bot{align-self:flex-start;background:" + colors.surface + ";border-bottom-left-radius:3px}" +
      ".msg.note{align-self:center;background:transparent;font-size:11.5px;opacity:.6;font-style:italic}" +
      ".cites{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}" +
      ".cite{font-size:10.5px;padding:2px 7px;border-radius:999px;background:" + colors.surface +
      ";border:1px solid " + colors.accent + ";color:" + colors.accent + "}" +
      ".badge{align-self:flex-start;font-size:10.5px;padding:2px 8px;border-radius:999px;background:" + colors.accent + ";color:#000;margin-top:4px}" +
      ".inputbar{display:flex;gap:8px;padding:12px;border-top:1px solid rgba(255,255,255,.08)}" +
      ".inputbar input{flex:1;padding:10px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.12);" +
      "background:" + colors.surface + ";color:" + colors.text + ";font-size:13.5px;outline:none}" +
      ".inputbar input:focus{border-color:" + colors.accent + "}" +
      ".inputbar button{border:none;border-radius:10px;padding:0 16px;cursor:pointer;font-size:14px;font-weight:600;" +
      "background:" + colors.accent + ";color:#000}" +
      ".inputbar button:disabled{opacity:.5;cursor:default}" +
      ".typing{display:inline-flex;gap:3px}" +
      ".typing span{width:6px;height:6px;border-radius:50%;background:" + colors.text + ";opacity:.5;animation:blink 1.2s infinite}" +
      ".typing span:nth-child(2){animation-delay:.2s}.typing span:nth-child(3){animation-delay:.4s}" +
      "@keyframes blink{0%,60%,100%{opacity:.2}30%{opacity:.9}}"
    );
  }

  var state = {
    branding: {
      display_name: COMPANY,
      tagline: "",
      greeting: "Hi! How can I help you today?",
      colors: DEFAULT_COLORS,
    },
  };

  // ── Render skeleton ───────────────────────────────────────────────────────
  var styleEl = document.createElement("style");
  root.appendChild(styleEl);

  var launcher = document.createElement("button");
  launcher.className = "launcher";
  launcher.setAttribute("aria-label", "Open support chat");
  launcher.textContent = "💬";
  root.appendChild(launcher);

  var panel = document.createElement("div");
  panel.className = "panel";
  panel.innerHTML =
    '<div class="header"><h3></h3><p></p></div>' +
    '<div class="log" role="log" aria-live="polite"></div>' +
    '<form class="inputbar">' +
    '<input type="text" placeholder="Type your question…" autocomplete="off" />' +
    "<button type=\"submit\">Send</button>" +
    "</form>";
  root.appendChild(panel);

  var logEl = panel.querySelector(".log");
  var form = panel.querySelector("form");
  var input = panel.querySelector("input");
  var sendBtn = panel.querySelector("button");
  var headerTitle = panel.querySelector(".header h3");
  var headerSub = panel.querySelector(".header p");

  function applyBranding(b) {
    state.branding = b;
    styleEl.textContent = styleBlock(b.colors || DEFAULT_COLORS);
    headerTitle.textContent = b.display_name || COMPANY;
    headerSub.textContent = b.tagline || "Support assistant";
  }
  applyBranding(state.branding);

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function addMessage(role, text, opts) {
    opts = opts || {};
    var el = document.createElement("div");
    el.className = "msg " + role;
    el.innerHTML = escapeHtml(text);
    if (opts.escalate) {
      var badge = document.createElement("div");
      badge.className = "badge";
      badge.textContent = "Escalating to a human";
      el.appendChild(badge);
    }
    if (opts.citations && opts.citations.length) {
      var wrap = document.createElement("div");
      wrap.className = "cites";
      opts.citations.forEach(function (c) {
        var chip = document.createElement("span");
        chip.className = "cite";
        chip.textContent = "📄 " + c.source;
        chip.title = c.snippet || "";
        wrap.appendChild(chip);
      });
      el.appendChild(wrap);
    }
    logEl.appendChild(el);
    logEl.scrollTop = logEl.scrollHeight;
    return el;
  }

  function addTyping() {
    var el = document.createElement("div");
    el.className = "msg bot";
    el.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
    logEl.appendChild(el);
    logEl.scrollTop = logEl.scrollHeight;
    return el;
  }

  var greeted = false;
  launcher.addEventListener("click", function () {
    var open = panel.classList.toggle("open");
    if (open) {
      input.focus();
      if (!greeted) {
        addMessage("bot", state.branding.greeting || "Hi! How can I help you today?");
        greeted = true;
      }
    }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    addMessage("user", text);
    input.value = "";
    input.disabled = true;
    sendBtn.disabled = true;
    var typing = addTyping();

    fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: COMPANY, message: text }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        typing.remove();
        addMessage("bot", data.answer, {
          citations: data.citations,
          escalate: data.escalate,
        });
        if (data.degraded) {
          addMessage("note", "(answered from help articles — language model offline)");
        }
      })
      .catch(function (err) {
        typing.remove();
        addMessage(
          "bot",
          "Sorry — I couldn't reach the assistant service. Please try again in a moment."
        );
        if (window.console) console.error("[customer-assistant]", err);
      })
      .finally(function () {
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
      });
  });

  // ── Fetch branding to theme the widget ───────────────────────────────────
  // API may be "" when the widget is served same-origin by the FastAPI app;
  // a relative fetch still resolves correctly in that case.
  fetch(API + "/companies/" + encodeURIComponent(COMPANY) + "/branding")
    .then(function (r) {
      return r.ok ? r.json() : null;
    })
    .then(function (b) {
      if (b) applyBranding(b);
    })
    .catch(function () {
      /* keep defaults if branding endpoint is unreachable */
    });
})();
