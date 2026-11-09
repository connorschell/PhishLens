/**
 * WBS 4.1 - service worker: registration, token custody, and the only place
 * that talks to the API.
 *
 * The content script runs in an isolated world on mail.google.com, but it is
 * still code living inside a page the extension does not control. The token
 * therefore never leaves this worker: the content script sends a message with
 * the scraped message, the worker attaches the Authorization header, and only
 * the resulting panel comes back. That also means a single place enforces
 * timeouts, backoff and the 401 re-registration path.
 *
 * MV3 service workers are evicted when idle, so nothing is held in memory that
 * matters. The token lives in chrome.storage.local and is read per request;
 * registrationInFlight only de-duplicates calls within one worker lifetime.
 */

import {
  API_BASE,
  CLIENT_PLATFORM,
  LOCAL_MODE,
  EXTENSION_VERSION,
  HOSTNAME_PENDING,
  INSTALL_ID_KEY,
  REGISTER_BACKOFF_MS,
  SCAN_TIMEOUT_MS,
  TOKEN_KEY,
} from "../config.js";

let registrationInFlight = null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function storedToken() {
  const bag = await chrome.storage.local.get(TOKEN_KEY);
  return bag[TOKEN_KEY] || null;
}

/**
 * Mint a per-install token, once. Concurrent callers share one attempt so a
 * burst of messages cannot mint a handful of installs for one browser.
 *
 * Backoff is deliberately slow: /register allows 10 calls an hour from one IP,
 * so a tight retry loop would spend the whole budget and then be unable to
 * register at all.
 */
async function register() {
  if (registrationInFlight) return registrationInFlight;

  registrationInFlight = (async () => {
    for (let attempt = 0; attempt <= REGISTER_BACKOFF_MS.length; attempt++) {
      try {
        const res = await fetch(`${API_BASE}/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            extension_version: EXTENSION_VERSION,
            client_platform: CLIENT_PLATFORM,
          }),
        });

        if (res.status === 201) {
          const body = await res.json();
          await chrome.storage.local.set({
            [TOKEN_KEY]: body.token,
            [INSTALL_ID_KEY]: body.install_id,
          });
          console.info("[PhishLens] registered install", body.install_id);
          return body.token;
        }

        // 429 and 503 are both "come back later". Anything else is a client
        // bug and retrying it just burns the rate limit.
        if (res.status !== 429 && res.status !== 503) {
          console.error("[PhishLens] registration refused:", res.status);
          return null;
        }
        const retryAfter = Number(res.headers.get("Retry-After")) * 1000;
        await sleep(retryAfter || REGISTER_BACKOFF_MS[attempt] || 300_000);
      } catch (err) {
        console.warn("[PhishLens] registration attempt failed:", err.message);
        await sleep(REGISTER_BACKOFF_MS[attempt] || 300_000);
      }
    }
    return null;
  })();

  try {
    return await registrationInFlight;
  } finally {
    registrationInFlight = null;
  }
}

async function token() {
  return (await storedToken()) || (await register());
}

/** POST to the API with the install token attached. Never returns the token. */
async function call(path, payload, { allowReregister = true } = {}) {
  const bearer = await token();
  if (!bearer) return { ok: false, reason: "unregistered" };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), SCAN_TIMEOUT_MS);

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${bearer}`,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (err) {
    return { ok: false, reason: err.name === "AbortError" ? "timeout" : "offline" };
  } finally {
    clearTimeout(timer);
  }

  // A 401 means this install was revoked or the server lost it. Re-register
  // exactly once; a loop here would hammer /register with a stale token.
  if (res.status === 401 && allowReregister) {
    await chrome.storage.local.remove([TOKEN_KEY, INSTALL_ID_KEY]);
    return call(path, payload, { allowReregister: false });
  }

  if (res.status === 429) {
    return { ok: false, reason: "rate_limited",
             retryAfter: Number(res.headers.get("Retry-After")) || 60 };
  }
  if (!res.ok) {
    return { ok: false, reason: "api_error", status: res.status };
  }
  return { ok: true, body: await res.json() };
}

/**
 * Message router. WBS 4.2 fills SCAN's payload from the Gmail DOM and 4.4
 * sends FEEDBACK; this worker does not care which produced it.
 */
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "SCAN") {
    call("/scan", msg.payload).then(sendResponse);
    return true;                       // keeps the channel open for the async reply
  }
  if (msg?.type === "FEEDBACK") {
    call("/feedback", msg.payload).then(sendResponse);
    return true;
  }
  return false;
});

chrome.runtime.onInstalled.addListener(async () => {
  if (LOCAL_MODE) {
    console.info("[PhishLens] local mode:", API_BASE,
                 "- start the stack with: docker compose up -d");
  }
  if (HOSTNAME_PENDING) {
    console.error(
      "[PhishLens] API_BASE is still the placeholder .invalid hostname. " +
      "Set it in config.js and in manifest.json host_permissions (A-17 item 3).",
    );
    return;
  }
  await register();
});
