/**
 * WBS 4.6 check - "Extension context invalidated" must not hang the panel.
 *
 * Run with:  node 04_Extension/tests/context_invalidated_check.js
 *
 * There is no JS test runner in this project, so this is a harness rather than
 * a suite: it loads content/gmail.js into a stubbed page and drives the three
 * cases that matter. It exists because the bug it covers cannot be found by
 * reading the code alone - the failure is a SYNCHRONOUS throw from
 * chrome.runtime.sendMessage, which skips the callback entirely and leaves the
 * panel sitting on its loading state forever.
 *
 * Expected output:
 *   no-id   -> loading, then "PhishLens needs a refresh"; observer stopped
 *   throw   -> loading, then "PhishLens needs a refresh"; observer stopped
 *   healthy -> loading, then verdict;                     observer still running
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SCRIPT = path.join(__dirname, "..", "content", "gmail.js");

function run(invalidateMode) {
  const calls = [];
  let observerDisconnected = false;

  const shadowRoot = { id: "shadow" };
  const host = {
    id: "phishlens-panel-host",
    shadowRoot,
    attachShadow: () => shadowRoot,
    parentElement: null,
    remove() {},
  };
  const container = {
    parentElement: { insertBefore() {} },
    getAttribute: () => "msg-1",
  };

  const sandbox = {
    console: { warn: (...a) => calls.push(["warn", a.join(" ")]), log() {} },
    setTimeout: (fn) => { fn(); return 1; },
    clearTimeout: () => {},
    Symbol,
    document: {
      body: {},
      getElementById: () => host,
      createElement: () => host,
      querySelector: () => container,
    },
    MutationObserver: class {
      observe() {}
      disconnect() { observerDisconnected = true; }
    },
    PhishLensParse: {
      extract: () => ({ subject: "x", body_text: "y" }),
      looksLikeAMessage: () => true,
    },
    PhishLensPanel: {
      loading: () => calls.push(["loading"]),
      message: (_r, title) => calls.push(["message", title]),
      failure: (_r, reason) => calls.push(["failure", reason]),
      verdict: () => calls.push(["verdict"]),
    },
    chrome: {
      runtime: {
        // An undefined id is Chrome's signal that the context is gone.
        get id() {
          return invalidateMode === "no-id" ? undefined : "abcdef";
        },
        lastError: undefined,
        sendMessage(msg, cb) {
          if (invalidateMode === "throw") {
            throw new Error("Extension context invalidated.");
          }
          cb({ ok: true, body: {} });
        },
      },
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SCRIPT, "utf8"), sandbox);
  return { calls, observerDisconnected };
}

let failures = 0;
function check(label, condition) {
  console.log(`  ${condition ? "PASS" : "FAIL"}  ${label}`);
  if (!condition) failures += 1;
}

for (const mode of ["no-id", "throw", "healthy"]) {
  const { calls, observerDisconnected } = run(mode);
  const kinds = calls.map((c) => c[0]);
  console.log(`\n--- ${mode}: ${JSON.stringify(calls)}`);

  if (mode === "healthy") {
    check("renders a verdict", kinds.includes("verdict"));
    check("observer still running", observerDisconnected === false);
  } else {
    check("does not stop at loading", kinds[kinds.length - 1] !== "loading");
    check("shows the refresh message",
      calls.some((c) => c[0] === "message" && /refresh/i.test(c[1])));
    check("observer disconnected", observerDisconnected === true);
  }
}

console.log(failures === 0 ? "\nAll checks passed." : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
