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

  function sendFeedback(scanId, disagreement) {
    chrome.runtime.sendMessage(
      { type: "FEEDBACK", payload: { scan_id: scanId, disagreement } },
      (res) => {
        // Deliberately quiet. The panel has already thanked the user; a late
        // error here would contradict what they were just told, and the
        // submission is a review signal, not something they are waiting on.
        if (!res?.ok) console.warn("[PhishLens] feedback not recorded:", res?.reason);
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

    chrome.runtime.sendMessage({ type: "SCAN", payload }, (res) => {
      // The user may have moved to another message while this was in flight.
      // Drawing a stale verdict over a different email is the one failure that
      // would actively mislead someone, so late replies are dropped.
      if (inFlight !== token) return;

      if (chrome.runtime.lastError) {
        PhishLensPanel.failure(host.shadowRoot, "offline");
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

  new MutationObserver(() => {
    clearTimeout(debounce);
    debounce = setTimeout(sync, DEBOUNCE_MS);
  }).observe(document.body, { childList: true, subtree: true });

  sync();
})();
