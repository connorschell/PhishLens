/**
 * WBS 4.1 mounting + WBS 4.2/4.3 orchestration.
 *
 * Gmail is a single-page application: it swaps the conversation in place and
 * never reloads, so there is no load event to hang this on. A debounced
 * MutationObserver is the only reliable signal, and it is debounced because
 * Gmail mutates that subtree constantly while rendering.
 *
 * This file decides WHEN to act. It does not know how to read a message
 * (parse.js) or how to draw one (panel.js), so when Gmail changes its markup
 * only parse.js needs repairing.
 */

(function () {
  "use strict";

  const MOUNT_ID = "phishlens-panel-host";
  const DEBOUNCE_MS = 250;

  let debounce = null;
  let currentKey = null;
  let inFlight = null;
  let observer = null;
  let contextLost = false;

  /**
   * WBS 4.6 - surviving "Extension context invalidated".
   *
   * When the extension is reloaded, updated or disabled, this content script
   * keeps running in the page Gmail already rendered, but its connection to
   * the extension is severed. chrome.runtime.sendMessage then throws
   * SYNCHRONOUSLY and the callback never runs - so the panel sat on its
   * loading state forever, and the MutationObserver went on calling a dead API
   * on every Gmail mutation. A spinner that never resolves is worse than an
   * error: it reads as "still checking" on a message that was never checked.
   *
   * chrome.runtime.id going undefined is the documented signal. The property
   * access is itself guarded because in some invalidation paths it throws
   * rather than returning undefined.
   */
  function contextAlive() {
    try {
      return Boolean(chrome.runtime?.id);
    } catch {
      return false;
    }
  }

  /**
   * One way in and out for every call to the worker. Normalises the three
   * distinct failures - dead context, dropped port, error response - so no
   * caller can forget one and leave the panel hanging.
   *
   * `cb(response, reason)`: exactly one is non-null.
   */
  function send(message, cb) {
    if (!contextLost && !contextAlive()) contextLost = true;
    if (contextLost) {
      cb(null, "extension_reloaded");
      return;
    }
    try {
      chrome.runtime.sendMessage(message, (res) => {
        if (chrome.runtime.lastError) {
          // lastError must be read, not just checked, or Chrome logs it as
          // an unchecked runtime error on every failed send.
          const msg = chrome.runtime.lastError.message || "";
          cb(null, /context invalidated|Extension context/i.test(msg)
            ? "extension_reloaded" : "offline");
          return;
        }
        cb(res, null);
      });
    } catch (err) {
      // The synchronous throw this task exists for.
      contextLost = true;
      cb(null, /context invalidated/i.test(String(err?.message))
        ? "extension_reloaded" : "offline");
    }
  }

  /**
   * Terminal state. Nothing in this page can recover - a reload of the tab is
   * the only fix - so the observer is disconnected rather than left firing
   * against an API that will keep throwing.
   */
  function standDown(shadowRoot) {
    contextLost = true;
    inFlight = null;
    clearTimeout(debounce);
    observer?.disconnect();
    if (shadowRoot) {
      PhishLensPanel.message(shadowRoot,
        "PhishLens needs a refresh",
        "The extension was updated or reloaded, so this tab lost its connection to it. " +
        "Reload Gmail to start checking messages again. This message was not checked.");
    }
  }

  const openMessage = () =>
    document.querySelector('div[role="main"] div[data-message-id]');

  function mount(container) {
    let host = document.getElementById(MOUNT_ID);
    if (!host) {
      host = document.createElement("div");
      host.id = MOUNT_ID;
      host.attachShadow({ mode: "open" });
    }
    if (host.parentElement !== container.parentElement) {
      container.parentElement?.insertBefore(host, container);
    }
    return host;
  }

  function unmount() {
    document.getElementById(MOUNT_ID)?.remove();
    currentKey = null;
  }

  /**
   * WBS 4.4 - hand the report to the worker and tell the panel what happened.
   *
   * The result is reported back rather than swallowed. A user who was told
   * their report was recorded, when it was not, has been lied to about the one
   * thing the control promises.
   */
  function sendFeedback(scanId, disagreement, note, done) {
    send(
      { type: "FEEDBACK", payload: { scan_id: scanId, disagreement, note: note || null } },
      (res, reason) => {
        // WBS 4.6: done() has to be called on every path. The control shows a
        // pending state until it fires, so an unanswered callback leaves the
        // user's report looking like it is still being sent.
        if (reason === "extension_reloaded") {
          console.warn("[PhishLens] feedback not recorded: extension reloaded");
          done(false, "extension_reloaded");
          return;
        }
        if (reason || !res?.ok) {
          const why = reason || res?.reason || "offline";
          console.warn("[PhishLens] feedback not recorded:", why);
          done(false, why);
          return;
        }
        done(true);
      },
    );
  }

  async function scan(container, host) {
    const payload = PhishLensParse.extract(container);

    // An empty payload means the parser found nothing - almost always because
    // Gmail changed its markup. Scoring it anyway would produce a confident
    // verdict about nothing, so say so instead.
    if (!PhishLensParse.looksLikeAMessage(payload)) {
      PhishLensPanel.message(host.shadowRoot,
        "Couldn’t read this message",
        "PhishLens could not find the message content on the page. This usually means Gmail changed its layout.");
      return;
    }

    PhishLensPanel.loading(host.shadowRoot);

    const token = Symbol("scan");
    inFlight = token;

    send({ type: "SCAN", payload }, (res, reason) => {
      // The user may have moved to another message while this was in flight.
      // Drawing a stale verdict over a different email is the one failure that
      // would actively mislead someone, so late replies are dropped.
      // A lost context is the exception: it is terminal for the whole tab, not
      // for this one scan, so it is handled even if the user has moved on.
      if (reason === "extension_reloaded") {
        standDown(inFlight === token ? host.shadowRoot : null);
        return;
      }
      if (inFlight !== token) return;

      if (reason) {
        PhishLensPanel.failure(host.shadowRoot, reason);
        return;
      }
      if (!res || !res.ok) {
        PhishLensPanel.failure(host.shadowRoot, res?.reason || "api_error", res?.retryAfter);
        return;
      }
      PhishLensPanel.verdict(host.shadowRoot, res.body, sendFeedback);
    });
  }

  function sync() {
    // WBS 4.6. Once the context is gone nothing here can succeed, and the
    // observer fires on every Gmail mutation - without this, a reloaded
    // extension produced a steady stream of thrown errors for as long as the
    // tab stayed open.
    if (contextLost) return;
    const container = openMessage();
    if (!container) {
      inFlight = null;
      unmount();
      return;
    }
    const key = container.getAttribute("data-message-id");
    if (key === currentKey) return;

    currentKey = key;
    scan(container, mount(container));
  }

  // Held in a variable so standDown() can disconnect it (WBS 4.6).
  observer = new MutationObserver(() => {
    clearTimeout(debounce);
    debounce = setTimeout(sync, DEBOUNCE_MS);
  });
  observer.observe(document.body, { childList: true, subtree: true });

  sync();
})();
