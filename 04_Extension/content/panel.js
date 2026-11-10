/**
 * WBS 4.3 - the panel.
 *
 * Renders one /scan response, and every state that is not a /scan response,
 * into the shadow root mounted by gmail.js. Built against the mockups in
 * 06_Deliverables/gui/mockups/panel_and_dashboard_mockups.html.
 *
 * Two rules it follows strictly:
 *
 * 1. It computes nothing. The score, the tier, the headline, the advice, the
 *    ranked signals and the bar widths all arrive from the server. If the panel
 *    derived the tier from the score itself, the extension and the server could
 *    disagree, and the user would be reading a verdict no model produced.
 * 2. Every string from the server is inserted as text, never as markup. The
 *    server is trusted, but a message body is not, and anything that originates
 *    in an email must never become live HTML inside Gmail's page.
 *
 * All styling lives in the shadow root, so Gmail's stylesheet cannot reach it
 * and it cannot reach Gmail's.
 */

var PhishLensPanel = (function () {
  "use strict";

  const TIER_COLOR = {
    clear:      { ink: "#2e6b41", bg: "#e9f2ec" },
    caution:    { ink: "#8a6a12", bg: "#f7f1e0" },
    suspicious: { ink: "#a1521a", bg: "#f8ece2" },
    dangerous:  { ink: "#9c2d24", bg: "#f8e9e7" },
  };

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .p { font: 13px/1.45 -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
         color: #1f2328; background: #fff; border: 1px solid #e2e4e7;
         border-radius: 6px; overflow: hidden; }
    .head { display: flex; align-items: center; gap: 8px; padding: 10px 14px;
            border-bottom: 1px solid #f0f1f3; }
    .mark { width: 14px; height: 14px; flex: none; }
    .word { font-weight: 600; font-size: 12.5px; }
    .right { margin-left: auto; font: 10px ui-monospace, Consolas, monospace; color: #8b929a; }
    .verdict { display: flex; gap: 14px; padding: 15px 14px 14px; }
    .dial { position: relative; width: 58px; height: 58px; flex: none; }
    .dial .n { position: absolute; inset: 0; display: grid; place-items: center;
               font-size: 20px; font-weight: 600; }
    .tier { display: inline-block; font: 500 10px ui-monospace, Consolas, monospace;
            letter-spacing: .12em; text-transform: uppercase; padding: 3px 7px;
            border-radius: 3px; margin-bottom: 7px; }
    .hl { font-size: 13.5px; font-weight: 600; margin: 0 0 5px; }
    .ad { font-size: 12.5px; color: #5c636b; margin: 0; }
    .bh { display: flex; justify-content: space-between; align-items: baseline;
          padding: 11px 14px 6px; border-top: 1px solid #f0f1f3; }
    .bh h4 { margin: 0; font-size: 10.5px; font-weight: 600; letter-spacing: .1em;
             text-transform: uppercase; color: #434a52; }
    .bh span { font: 10px ui-monospace, Consolas, monospace; color: #8b929a; }
    .sig { display: flex; gap: 10px; padding: 8px 14px; }
    .sig + .sig { border-top: 1px solid #f0f1f3; }
    .kind { flex: none; width: 38px; padding-top: 1px; font: 9px ui-monospace, Consolas, monospace;
            letter-spacing: .08em; text-transform: uppercase; color: #8b929a; }
    .kind.rule { color: #9c2d24; }
    .body { flex: 1; min-width: 0; }
    .txt { font-size: 12.5px; }
    .bar { height: 3px; background: #f0f1f3; border-radius: 2px; margin-top: 6px; overflow: hidden; }
    .bar i { display: block; height: 100%; background: #99a1a9; }
    .sig.rule .bar i { background: #9c2d24; opacity: .65; }
    .mit { padding: 10px 14px 12px; border-top: 1px solid #f0f1f3; background: #fbfbfc; }
    .mit h4 { margin: 0 0 5px; font-size: 10.5px; font-weight: 600; letter-spacing: .1em;
              text-transform: uppercase; color: #434a52; }
    .mit p { margin: 0; font-size: 12px; color: #5c636b; }
    .foot { display: flex; align-items: center; gap: 10px; padding: 9px 14px;
            border-top: 1px solid #f0f1f3; font: 10px ui-monospace, Consolas, monospace; color: #8b929a; }
    button { font: 11.5px -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #434a52;
             border: 1px solid #d8dbdf; background: #fff; padding: 4px 10px;
             border-radius: 4px; cursor: pointer; }
    button:hover { background: #f6f7f8; }
    button[disabled] { color: #9aa1a9; cursor: default; background: #fff; }
    .row { display: flex; gap: 8px; margin: 11px 0 0; }
    .row button { flex: 1; }
    .pad { padding: 14px; }
    .t { font-size: 13px; font-weight: 600; margin: 0; }
    .m { font-size: 12.5px; line-height: 1.55; color: #5c636b; margin: 8px 0 0; }
    .sk { height: 9px; border-radius: 3px; background: #eef0f2; }
    textarea.note { width: 100%; margin-top: 10px; padding: 7px 9px; resize: vertical;
             font: 12px -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #1f2328;
             border: 1px solid #d8dbdf; border-radius: 4px; background: #fff; }
    textarea.note:focus { outline: 2px solid #c9ced3; outline-offset: -1px; }
    textarea.note[disabled] { color: #8b929a; background: #fbfbfc; }
    .count { font: 10px ui-monospace, Consolas, monospace; color: #8b929a; margin-top: 4px; text-align: right; }
    .collapsed { display: flex; align-items: center; gap: 9px; padding: 10px 14px; }
    .collapsed .tier { margin: 0; }
  `;

  const MARK = `<svg class="mark" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="6.6" cy="6.6" r="4.7" fill="none" stroke="#1f2328" stroke-width="1.5"/>
      <path d="M10.2 10.2 L14 14" stroke="#1f2328" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`;

  /** Build an element with text content. Text, never markup - see rule 2. */
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  function shell(root) {
    root.innerHTML = "";
    const style = document.createElement("style");
    style.textContent = CSS;
    root.appendChild(style);
    const p = el("div", "p");
    root.appendChild(p);
    return p;
  }

  function header(p, rightText) {
    const h = el("div", "head");
    h.innerHTML = MARK;                       // static markup of our own, no input
    h.appendChild(el("span", "word", "PhishLens"));
    if (rightText) h.appendChild(el("span", "right", rightText));
    p.appendChild(h);
    return h;
  }

  /** The score ring. Stroke length is the score, so the ring is the number. */
  function dial(score, color) {
    const wrap = el("div", "dial");
    const C = 153.9;                                   // 2 * pi * 24.5
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 58 58");
    svg.innerHTML =
      `<circle cx="29" cy="29" r="24.5" fill="none" stroke="#eef0f2" stroke-width="5"/>` +
      `<circle cx="29" cy="29" r="24.5" fill="none" stroke="${color}" stroke-width="5"
               stroke-linecap="round" stroke-dasharray="${C}"
               stroke-dashoffset="${C - (C * Math.max(0, Math.min(100, score))) / 100}"
               transform="rotate(-90 29 29)"/>`;
    wrap.appendChild(svg);
    wrap.appendChild(el("div", "n", score));
    return wrap;
  }

  function tierBadge(severity) {
    const c = TIER_COLOR[severity] || TIER_COLOR.caution;
    const b = el("span", "tier", severity);
    b.style.color = c.ink;
    b.style.background = c.bg;
    return b;
  }

  // ---------------------------------------------------------------- states --

  function loading(root) {
    const p = shell(root);
    header(p, "scoring…");
    const v = el("div", "verdict");
    const ring = el("div", "sk");
    ring.style.cssText = "width:58px;height:58px;border-radius:50%;flex:none";
    const lines = el("div");
    lines.style.flex = "1";
    [40, 85, 66].forEach((w, i) => {
      const s = el("div", "sk");
      s.style.width = w + "%";
      if (i) s.style.marginTop = "8px";
      lines.appendChild(s);
    });
    v.append(ring, lines);
    p.appendChild(v);
  }

  function message(root, title, body, foot) {
    const p = shell(root);
    header(p);
    const pad = el("div", "pad");
    pad.appendChild(el("p", "t", title));
    if (body) pad.appendChild(el("p", "m", body));
    p.appendChild(pad);
    if (foot) p.appendChild(el("div", "foot", foot));
  }

  function failure(root, reason, retryAfter) {
    if (reason === "rate_limited") {
      const secs = retryAfter || 60;
      const when = secs <= 90 ? "in about a minute"
                 : `in about ${Math.round(secs / 60)} minutes`;
      return message(root, "Too many messages scanned at once",
        `Checking will start again ${when}. Your mail is unaffected.`);
    }
    if (reason === "unregistered") {
      return message(root, "PhishLens isn’t set up yet",
        "It couldn’t register with the scoring service. Check that the API address is configured and the service is running.");
    }
    // timeout, offline, api_error, and anything unforeseen land here. The
    // wording never implies the message is safe - silence reads as "fine", and
    // this is the state most likely to be seen during a demo.
    return message(root, "Can’t check this message right now",
      "Judge it yourself: check the sender’s address, and don’t enter a password from a link in an email.");
  }

  // --------------------------------------------------------------- verdict --

  function verdict(root, scan, onFeedback) {
    const color = (TIER_COLOR[scan.severity] || TIER_COLOR.caution).ink;
    const p = shell(root);
    header(p);

    // Clear collapses to a single line. A panel that announces "fine" on every
    // message in full is a panel users stop seeing - including on the one that
    // matters.
    if (scan.severity === "clear") {
      const row = el("div", "collapsed");
      row.appendChild(tierBadge("clear"));
      row.appendChild(el("span", "ad", scan.headline || "Nothing unusual found."));
      p.appendChild(row);
      return;
    }

    const v = el("div", "verdict");
    v.appendChild(dial(scan.risk_score, color));
    const copy = el("div");
    copy.appendChild(tierBadge(scan.severity));
    copy.appendChild(el("p", "hl", scan.headline));
    if (scan.advice) copy.appendChild(el("p", "ad", scan.advice));
    v.appendChild(copy);
    p.appendChild(v);

    const signals = Array.isArray(scan.signals) ? scan.signals : [];
    if (signals.length) {
      const bh = el("div", "bh");
      bh.appendChild(el("h4", null, "Why this score"));
      bh.appendChild(el("span", null, `${signals.length} of ${scan.signals_considered} signals`));
      p.appendChild(bh);

      for (const s of signals) {
        const row = el("div", "sig" + (s.kind === "rule" ? " rule" : ""));
        row.appendChild(el("div", "kind" + (s.kind === "rule" ? " rule" : ""), s.kind));
        const body = el("div", "body");
        body.appendChild(el("div", "txt", s.text));
        // share is null for rule signals, which have no model contribution.
        const bar = el("div", "bar");
        const fill = el("i");
        fill.style.width = Math.round((s.share != null ? s.share : 1) * 100) + "%";
        bar.appendChild(fill);
        body.appendChild(bar);
        row.appendChild(body);
        p.appendChild(row);
      }
    }

    const mitigating = Array.isArray(scan.mitigating) ? scan.mitigating : [];
    if (mitigating.length) {
      const m = el("div", "mit");
      m.appendChild(el("h4", null, "Pointing the other way"));
      m.appendChild(el("p", null, mitigating.map((x) => x.text).join(" ")));
      p.appendChild(m);
    }

    const foot = el("div", "foot");
    foot.appendChild(el("span", null,
      `scored in ${scan.duration_ms} ms${scan.persisted ? "" : " · not recorded"}`));

    // WBS 4.4 hooks in here. No scan_id means the scan was not recorded, so
    // there is nothing for feedback to attach to and the control is omitted
    // rather than shown and failing.
    if (scan.scan_id != null && typeof onFeedback === "function") {
      const b = el("button", null, "This looks wrong");
      b.addEventListener("click", () => feedbackPrompt(root, scan, onFeedback));
      foot.appendChild(b);
    }
    p.appendChild(foot);
  }

  /**
   * WBS 4.4 - the feedback control.
   *
   * Two choices and an optional note. The note is capped at 500 characters to
   * match the CHECK constraint on the feedback table, so an over-long note is
   * refused here rather than bouncing off the database.
   *
   * The thank-you is NOT shown optimistically. Telling the user their report
   * was recorded and then silently dropping it is worse than telling them it
   * failed: the whole point of the control is that someone will look at what
   * they sent. So the panel waits for the worker's answer and says which
   * happened.
   */
  function feedbackPrompt(root, scan, onFeedback) {
    const p = shell(root);
    header(p, "scan " + scan.scan_id);
    const pad = el("div", "pad");
    pad.appendChild(el("p", "t", "What did it get wrong?"));

    const note = document.createElement("textarea");
    note.placeholder = "Add a note (optional)";
    note.maxLength = 500;
    note.rows = 2;
    note.className = "note";

    const count = el("div", "count", "0 / 500");
    note.addEventListener("input", () => {
      count.textContent = `${note.value.length} / 500`;
    });

    const row = el("div", "row");
    const safe = el("button", null, "This is safe");
    const phish = el("button", null, "This is phishing");

    const send = (kind) => {
      safe.disabled = true;
      phish.disabled = true;
      note.disabled = true;
      count.textContent = "sending…";

      onFeedback(scan.scan_id, kind, note.value.trim(), (ok, reason) => {
        const done = shell(root);
        header(done);
        const d = el("div", "pad");
        if (ok) {
          d.appendChild(el("p", "t", "Thanks — recorded."));
          d.appendChild(el("p", "m",
            "A person reviews these. It does not change the model on its own."));
        } else {
          d.appendChild(el("p", "t", "That didn’t send"));
          d.appendChild(el("p", "m",
            reason === "rate_limited"
              ? "Too many reports in a short time. Try again later."
              : "PhishLens couldn’t reach the service. Your report wasn’t recorded."));
          const retry = el("button", null, "Try again");
          retry.style.marginTop = "10px";
          retry.addEventListener("click", () => feedbackPrompt(root, scan, onFeedback));
          d.appendChild(retry);
        }
        done.appendChild(d);
      });
    };

    safe.addEventListener("click", () => send("false_positive"));
    phish.addEventListener("click", () => send("false_negative"));

    row.append(safe, phish);
    pad.append(row, note, count);
    p.appendChild(pad);
  }

  return { loading, verdict, failure, message };
})();
