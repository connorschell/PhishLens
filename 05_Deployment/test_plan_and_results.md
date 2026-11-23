# End-to-end test plan and results

**WBS 5.4** · PhishLens · Connor Schell · CYBR 498W
Deliverable #9 (test plan and test results). Drafted 2026-11-22; results filled
in on execution.

The system has been tested in pieces — unit tests on the parser, the feature
extractor, the contribution maths, the Safe Browsing degradation paths, the API
routes. This is the first test of the whole chain as a user meets it: a real
message open in a real Gmail tab, parsed from the rendered DOM, scored by the
deployed API over HTTPS, explained in the panel.

Two things from week 8 shape what is tested here. A message the model already
rates `dangerous` hides the effect of a rule-layer floor entirely, so cases that
exercise floors must use messages the model rates low. And a short, plainly
legitimate message carrying a `cnu.edu` link scored `dangerous` — a real false
positive, caused by the body-length feature dominating when there is little text
to weigh. That case is included deliberately; it is expected to fail until WBS
2.4 recalibrates, and it is more useful recorded as a known failure than left
out.

---

## 1. What is under test

| Layer | Component |
|---|---|
| Client | Chrome MV3 extension — `parse.js`, `panel.js`, `gmail.js`, service worker |
| Transport | HTTPS to `api.usephishlens.app`, Nginx → uvicorn |
| Server | `/register`, `/scan`, `/feedback`, rule layer, Safe Browsing |
| Data | PostgreSQL — scans, indicators, feedback, url_reputation |
| Operator | `/dashboard` — history, feedback queue, counts |

Out of scope: model quality. Precision, recall and false-positive rate come from
the held-out split in `02_Model/evaluate.py`, not from a handful of live
messages. What is tested here is whether the pipeline delivers the model's
verdict faithfully to the user.

## 2. Test accounts and seeding

Two throwaway Gmail accounts, neither linked to a personal identity:

| Account | Role |
|---|---|
| `phishlens.test.rx@gmail.com` | Receives the seeded corpus; the extension runs here |
| `phishlens.test.tx@gmail.com` | Sends the seeded messages |

Seeding is done by sending messages from the sender account to the receiver
account, drawn from the corpora already in `01_Data/processed/normalized/` plus
the hand-built cases below. Nothing is forwarded from a personal inbox.

**Phishing samples are sent with links defanged at the destination, not in the
text.** The URLs stay structurally intact — that is what the feature extractor
reads — but point at hosts under the author's control or at Google's canonical
test URLs. No live malicious URL is clicked, and no credential is ever entered.

Gmail will put much of this in Spam. That is expected and does not invalidate
the test: the extension runs against whatever message is open, including one
opened from the Spam folder. Where a message had to be retrieved from Spam, the
results table records it.

## 3. Prerequisites

- [ ] Deployed API answers `https://api.usephishlens.app/health` with 200
- [ ] Deployed commit matches local `HEAD` (the week-8 lesson: 3.5 was tested
      against a server running older code for a full round)
- [ ] `SAFE_BROWSING_API_KEY` present in the server `.env`
- [ ] `DASHBOARD_PASSWORD` set; `/dashboard` issues a session
- [ ] Extension loaded unpacked, `config.js` pointing at the deployed host, not
      `localhost`
- [ ] Extension storage cleared so `/register` is exercised from a cold start
- [ ] WBS 5.3 backup taken before the run, so the seeded rows can be removed
      afterwards without losing earlier data

## 4. Test cases

Pass criteria are written so that a result is either met or not. "Looks right"
is not a pass.

### Group A — registration and transport

| ID | Case | Procedure | Pass criteria |
|---|---|---|---|
| A1 | Cold-start registration | Clear extension storage, open any message | One `POST /register`; token stored in `chrome.storage.local`; no second registration on later messages |
| A2 | Token reuse | Open five messages | Exactly zero further `/register` calls; all `/scan` calls carry the token |
| A3 | TLS | Inspect the request in DevTools | All traffic HTTPS; no mixed-content or certificate warning |
| A4 | No secret in the bundle | `grep` the unpacked extension for the signing secret and the Safe Browsing key | Neither present (A-02 requirement) |
| A5 | Unauthenticated degradation | Delete the stored token mid-session, open a message | `/scan` still returns a score; panel renders; behaviour matches Change Log #16 |

### Group B — parsing against live Gmail

| ID | Case | Procedure | Pass criteria |
|---|---|---|---|
| B1 | Plain-text message | Open a seeded text-only message | Sender address, subject, body and link set match the message as displayed |
| B2 | HTML message with images | Open a seeded HTML newsletter | Links extracted with anchor text; image-only content does not produce an empty body error |
| B3 | Reply with quoted history | Reply to a seeded phishing message, open the reply | Quoted text excluded — the reply is scored, not the thread (WU7 design decision) |
| B4 | Display-name spoof | Message with display name `CNU IT Support`, unrelated sender domain | `sender_mismatch` present in the indicators; named in the explanation |
| B5 | Conversation view | Open a thread with four messages, expand the newest | The open message is scored, not the first in the thread |
| B6 | Selector resilience | Confirm no uncaught exception on any of B1–B5 | `parse.js` yields empty fields rather than throwing; panel never disappears |

### Group C — scoring, tiers, explanations

| ID | Case | Procedure | Pass criteria |
|---|---|---|---|
| C1 | Clear tier | Open an ordinary legitimate message | Tier `clear`; panel collapses to one line (WU7 decision) |
| C2 | Dangerous tier | Open a seeded phishing message from the corpus | Tier `dangerous`; ranked explanation lists real contributions |
| C3 | Explanation fidelity | Compare three panel reasons against `/scan` JSON | Every displayed reason corresponds to a contribution or rule hit in the response; nothing invented client-side |
| C4 | Panel computes nothing | Alter `severity` in a replayed response | Panel displays the altered tier — confirming it is not deriving one locally |
| C5 | No HTML injection | Seed a message whose subject contains `<img src=x onerror=alert(1)>` | Rendered as text in the panel; no script executes; no Gmail DOM corruption |
| C6 | Safe Browsing floor visible | Message the model rates `caution` whose only problem is a flagged destination | `severity` raised; `severity_floored_by` names the rule; `model_severity` shows the unfloored tier |
| C7 | Safe Browsing degradation | Remove the API key, restart, rescan C6 | Scan still returns; tier falls back to the model's own; no error surfaced to the user |
| C8 | Cache behaviour | Rescan C6 within the TTL | No second outbound Lookup call; verdict identical |

### Group D — known-failure cases

Recorded, not skipped. These are the cases WBS 2.4 exists to fix.

| ID | Case | Expected today | Target after 2.4 |
|---|---|---|---|
| D1 | Short legitimate message with a `cnu.edu` link | `dangerous` — body-length feature dominates | `clear` or `caution` |
| D2 | Modern legitimate bulk mail (receipt, shipping notice, university notice) | Over-flagged; the vintage gap documented in `01_Data/CORPUS.md` | False-positive rate on ordinary correspondence at or under the tier budget |
| D3 | Legitimate message with a tracking redirector | Likely `suspicious` | Not above `caution` |

### Group E — feedback and operator view

| ID | Case | Procedure | Pass criteria |
|---|---|---|---|
| E1 | Disagreement recorded | Use the feedback control on D1 | Panel waits for the server and confirms; row appears in the dashboard feedback queue |
| E2 | Feedback failure handling | Stop the API, submit feedback | Panel reports failure and offers retry; never claims success (WU7 decision) |
| E3 | Scan history | Open the dashboard after the run | Every scan from this session present with its tier |
| E4 | No message content stored | Inspect the `scans` row for C2 | Fingerprint only; no subject, body or address |
| E5 | Metrics labelling | Read the dashboard metrics panel | Labelled as operational counts; the word "accuracy" does not appear |

### Group F — failure and recovery

| ID | Case | Procedure | Pass criteria |
|---|---|---|---|
| F1 | API unreachable | Stop the API, open a message | Panel shows a terminal error state; no indefinite spinner |
| F2 | Extension context invalidated | Reload the extension with a Gmail tab open, then open a message | Terminal state, not a hang; MutationObserver disconnected (WBS 4.6) |
| F3 | Slow response | Throttle to 3G, open a message | Loading state resolves; no duplicate `/scan` |
| F4 | Rate limit | Open messages rapidly past the per-token limit | 429 handled gracefully; panel explains rather than hanging |
| F5 | Recovery | Restart the API, open a new message | Normal scoring resumes with no extension reload |

## 5. Results

Fill one row per case on execution. `Evidence` is a screenshot path under
`06_Deliverables/gui/e2e/` or a DevTools capture.

| ID | Date | Result | Evidence | Notes |
|---|---|---|---|---|
| A1 | | | | |
| A2 | | | | |
| A3 | | | | |
| A4 | | | | |
| A5 | | | | |
| B1 | | | | |
| B2 | | | | |
| B3 | | | | |
| B4 | | | | |
| B5 | | | | |
| B6 | | | | |
| C1 | | | | |
| C2 | | | | |
| C3 | | | | |
| C4 | | | | |
| C5 | | | | |
| C6 | | | | |
| C7 | | | | |
| C8 | | | | |
| D1 | | | | |
| D2 | | | | |
| D3 | | | | |
| E1 | | | | |
| E2 | | | | |
| E3 | | | | |
| E4 | | | | |
| E5 | | | | |
| F1 | | | | |
| F2 | | | | |
| F3 | | | | |
| F4 | | | | |
| F5 | | | | |

### Summary

_Completed on execution: cases run, passed, failed, deferred; defects raised and
where they were tracked._

## 6. Cleanup

- [ ] Delete seeded rows from `scans`, `indicators`, `feedback` (or restore the
      pre-run backup from WBS 5.3)
- [ ] Revoke the test install's token
- [ ] Leave the test Gmail accounts in place until after the final demo

## 7. Relationship to the final evaluation

This plan answers "does the system work". WBS 5.5 answers "how well does it
classify", on the held-out split, after WBS 1.6 rebuilds the legitimate half of
the corpus with modern mail. Both go into deliverable #9; neither substitutes
for the other. A live run over a few dozen seeded messages is not a measurement
of precision or recall and is not reported as one.
