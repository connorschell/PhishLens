/**
 * WBS 4.2 - reading the open message out of the Gmail page.
 *
 * This is the most fragile file in the project and it is isolated on purpose.
 * Gmail's markup is generated: class names like "a3s" and "hP" are build
 * artifacts, not an API, and Google changes them without notice or warning.
 * Nothing else in the extension knows these selectors exist, so when Gmail
 * breaks the extension, this file is the only one that needs repairing.
 *
 * Three rules shape what follows:
 *
 * 1. Prefer attributes over classes. [data-message-id] and span[email] have
 *    been stable for years; the obfuscated class names have not. Where a class
 *    is unavoidable it is listed alongside fallbacks rather than alone.
 * 2. Never throw. A selector that stops matching returns an empty field, and
 *    the server scores what it was given - the API treats every field as
 *    optional. A parser that threw would take the whole panel down over one
 *    missing attachment name.
 * 3. Bound every field here as well as on the server. The server rejects an
 *    oversized payload with a 422, which is correct but useless to the user;
 *    truncating client side means a 300,000 word thread still gets scored.
 *
 * Content scripts are not modules, so this attaches to one global on the
 * isolated world. Gmail's own page scripts cannot see it.
 */

var PhishLensParse = (function () {
  "use strict";

  // Mirrors app/config.py. Kept slightly under the server's limits so a
  // boundary case truncates here rather than bouncing off a 422.
  const MAX_SUBJECT = 990;
  const MAX_TEXT = 199_000;
  const MAX_HTML = 499_000;
  const MAX_ATTACHMENTS = 25;

  const clip = (s, n) => (typeof s === "string" ? s.slice(0, n) : "");

  /** First element matching any selector in the list, or null. */
  function pick(root, selectors) {
    for (const sel of selectors) {
      try {
        const el = root.querySelector(sel);
        if (el) return el;
      } catch (_) { /* a malformed selector must not take the parser down */ }
    }
    return null;
  }

  /**
   * Sender. Gmail renders this as <span email="..." name="...">, and that
   * attribute pair has outlived several redesigns of everything around it.
   */
  function sender(container) {
    const el = pick(container, ["span[email]", "span[data-hovercard-id]"]);
    if (!el) return { display: "", address: "" };
    const address = el.getAttribute("email") ||
                    el.getAttribute("data-hovercard-id") || "";
    // The name attribute is the display name Gmail parsed from the header.
    // Its text content is what the user actually sees, which is what matters
    // for a display-name spoof, so text wins when the two disagree.
    const display = (el.textContent || "").trim() || el.getAttribute("name") || "";
    return { display: clip(display, 400), address: clip(address, 320) };
  }

  /**
   * Reply-To. Gmail does not render this in the collapsed header; it lives in
   * the "show details" table, which is only in the DOM once the user has
   * opened it. So this is genuinely absent most of the time, and the feature
   * extractor already treats an empty reply-to as "not observed" rather than
   * as "same as sender" - an important distinction, because guessing here
   * would manufacture a signal that was never measured.
   */
  function replyTo(container) {
    const row = pick(container, ["tr.iv span[email]", "table.cf span[email]"]);
    return row ? clip(row.getAttribute("email") || "", 320) : "";
  }

  /** Subject. Lives above the message, in the thread header, not inside it. */
  function subject(container) {
    const el = pick(document, ["h2[data-thread-perm-id]", "h2.hP", "h2.ha"]) ||
               pick(container, ["h2"]);
    return clip(el ? (el.textContent || "").trim() : "", MAX_SUBJECT);
  }

  /**
   * Body. div.a3s is the rendered message. Quoted history (.gmail_quote) and
   * the signature are stripped: a reply that quotes a phishing message is not
   * itself phishing, and leaving the quote in would score the thread rather
   * than the message in front of the user.
   */
  function body(container) {
    const el = pick(container, ["div.a3s", "div[data-message-id] div.ii", "div.ii"]);
    if (!el) return { text: "", html: "" };

    // Work on a copy; removing nodes from Gmail's live DOM would blank the
    // message the user is reading.
    const copy = el.cloneNode(true);
    copy.querySelectorAll("blockquote.gmail_quote, div.gmail_quote, div.gmail_signature")
        .forEach((n) => n.remove());

    return {
      text: clip((copy.innerText || copy.textContent || "").trim(), MAX_TEXT),
      html: clip(copy.innerHTML || "", MAX_HTML),
    };
  }

  /**
   * Attachments. Only the metadata the server actually uses - name, type and
   * size. The file itself is never read, never uploaded and never touched.
   * Gmail renders the size as text like "(142 KB)", so it is parsed back to
   * bytes here; when it cannot be parsed the size is reported as 0, which the
   * feature extractor reads as unknown rather than as empty.
   */
  function attachments(container) {
    const out = [];
    const nodes = container.querySelectorAll("span.aZo, div.aQH span.aV3, span.aV3");
    for (const n of nodes) {
      if (out.length >= MAX_ATTACHMENTS) break;
      // Gmail's download_url is "mimetype:filename:url" - three fields, and
      // the url itself contains colons, so split with a limit and take the
      // middle rather than the last segment.
      const raw = n.getAttribute("download_url") || "";
      const parts = raw.split(":");
      const fromAttr = parts.length >= 3 ? parts[1] : "";
      const filename = fromAttr || (n.textContent || "").trim();
      if (!filename) continue;
      const label = n.closest("span.aZo, div.aQH")?.textContent || "";
      out.push({
        filename: clip(filename, 400),
        content_type: clip(parts.length >= 3 ? parts[0] : (n.getAttribute("type") || ""), 200),
        size_bytes: parseSize(label),
      });
    }
    return out;
  }

  function parseSize(text) {
    const m = /\(?([\d.]+)\s*(bytes|KB|MB|GB)\)?/i.exec(text || "");
    if (!m) return 0;
    const n = parseFloat(m[1]);
    if (!isFinite(n)) return 0;
    const unit = m[2].toLowerCase();
    const mult = unit === "gb" ? 1e9 : unit === "mb" ? 1e6 : unit === "kb" ? 1e3 : 1;
    return Math.round(n * mult);
  }

  /**
   * Assemble the payload the API expects. Field names match ScanRequest in
   * 03_Backend/app/schemas.py exactly; a rename on either side breaks the
   * contract, which is why 03_Backend/API_CONTRACT.md is the reference for both.
   */
  function extract(container) {
    const who = sender(container);
    const text = body(container);
    return {
      from_display: who.display,
      from_address: who.address,
      reply_to_address: replyTo(container),
      subject: subject(container),
      body_text: text.text,
      body_html: text.html,
      attachments: attachments(container),
    };
  }

  /**
   * Did the parser actually find a message? Used to decide whether to scan at
   * all. Scoring an empty payload would produce a confident-looking verdict
   * about nothing, which is worse than showing no panel.
   */
  function looksLikeAMessage(payload) {
    return Boolean(payload.subject || payload.body_text || payload.from_address);
  }

  return { extract, looksLikeAMessage, _internals: { sender, subject, body, attachments, parseSize } };
})();
