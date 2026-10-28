# Week 5 standup — speaking notes

Connor Schell · CYBR 498W · 28 October 2026 · ~3 minutes

---

## Q1 — What I did, and how long

**15 hours. I built the backend. Three pieces — all finished October 21, a week
before they were due.**

**The database design — 5.5 hrs.**
Six tables: installations, model versions, scans, the individual signals behind
each scan, a cache for link reputation, and user feedback.

> The decision worth mentioning: last week I had an open question about whether
> the extension sends the message to the server or only the numbers measured from
> it. I went with sending the message — but **nothing about the message is
> stored.** The scans table has no column that can hold a subject, a body, or a
> sender. Not "we promise not to" — there is physically nowhere to put it. Storing
> it would take a migration someone has to write on purpose.

**Building it — 2.5 hrs.**
The schema as a migration the container runs on first start, plus seed scripts
that register a trained model with its thresholds, so every scan records which
model version produced it. Without that, a result I look at in three weeks can't
be attributed to a model.

**The API — 7 hrs.**
Two endpoints. `/scan` takes a message and returns the score and the explanation.
`/health` reports whether the model and the database are up, separately.

Two things I'd point at:

- **There's only one scoring implementation.** The API calls the same four
  modules the demo calls, in the same order. A test asserts the API's answer
  matches calling the model directly — field for field, including the order of
  the explanation sentences. Two copies that drift is the failure I was most
  worried about.
- **The verdict doesn't depend on the database.** If storage is down you still
  get your score; the response just says it wasn't recorded. Withholding a
  phishing warning to protect a history feature is the wrong trade.

83 milliseconds per scan. 75 tests, all passing.

---

## If he asks why I can't show it running

Say it plainly — this is on schedule, not behind:

> "The backend runs — I can score a message and get the explanation back on my
> own machine today. What doesn't exist yet is the two things that make it
> *demoable*: the server it'll be hosted on, and the extension UI. Those are
> weeks 6 and 7. The live demo is Intermediate Milestone 2 on November 9, which
> is where the proposal always had it."

**You are not empty-handed.** You can open
`06_Deliverables/IM1_demo/PhishLens_IM1_demo.html` on any laptop with no setup —
four real messages scored and rendered as the panel will look. If he wants to see
something, that's the thing to open.

---

## Q2 — Next week

- **The feedback endpoint, per-install registration, and rate limiting** — 7 hrs.
  This is the authentication rewrite from the proposal feedback: no secret ships
  in the extension; each install gets its own token at first run, so one can be
  revoked without affecting anyone else.
- **Stand up the server** — provision the VPS, harden it, firewall, SSH keys —
  5 hrs. **I'm doing this first in the week, ahead of the API work.** It's the
  only task left that depends on things outside my control — domain, hosting
  account, DNS, certificate. The API is code I can write any time. Better to hit
  a problem with eleven days before the demo than with four.
- **Docker and Nginx with a TLS certificate** — 5 hrs.
- Outstanding accounts: a domain, the Safe Browsing key, two test Gmail accounts.

---

## Q3 — Changes against the proposal

**One change.** The data handling decision above — message sent, nothing stored.
No schedule impact. Doing feature extraction in the browser is still the better
end state; it needs the parser written a second time in JavaScript and kept in
exact step, and drift between the two is the defect I'd never notice. It's first
in line if I finish early.

**One risk, not yet a change.** The GitHub Student Pack has been pending since
September 30 — the hosting credit for the server depends on it. If it hasn't
cleared by the end of next week I'll pay for a basic server rather than let the
milestone demo wait on a third party.

---

## Likely follow-ups

**"How do you know the explanations are real?"**
They're computed from the model's own arithmetic, not guessed after the fact. The
decomposition is checked against the score across the whole held-out set — worst
error 1.6 × 10⁻¹⁴. No language model anywhere in the scoring path; every sentence
is a template over a measured number.

**"Where did the ablation land?"** (he may remember this from week 4)
Still open, deliberately. Removing the six suspect features drops recall from 85%
to 31% at the same false-positive budget. Corpus data can't tell me whether
they're real phishing structure or the twenty-year gap between my two corpora.
Live-Gmail testing in week 9 decides it. I'm carrying both sets of numbers until
then.

**"Why not use the Gmail API?"**
Locked in the proposal — DOM parsing, no OAuth, no account access. The tradeoff
is that the rendered page doesn't expose the authentication headers, so SPF and
DKIM aren't available to me.

**If asked something you don't know:** say you'll check and follow up. Don't
invent a number in front of him — the logbook has to match what you say.
