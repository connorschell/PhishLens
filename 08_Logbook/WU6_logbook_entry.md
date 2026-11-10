# Week 6 logbook entry — week ending 4 November 2026

PhishLens · CYBR 498W · Connor Schell

## Hours

14.5 hours, against 21.5 estimated for the WBS tasks scheduled this week. The
gap is not work left undone — 3.4 and 4.1 both finished — it is WBS 5.2, which
turned out to be blocked rather than unfinished and so consumed half an hour of
diagnosis instead of five hours of work. Running total 72.5 hours.

| Task | Hours | What was done |
|---|---|---|
| 3.4 | 7.0 | /register, /feedback, per-install token auth, rate limiting, CORS |
| 4.1 | 4.5 | MV3 scaffold, service worker, content-script mounting, wiring |
| A-19 | 2.0 | Interface mockups for the panel and the dashboard |
| A-08 | 1.0 | Weekly update |
| 5.2 | 0.5 | Diagnosis — found blocked, not unfinished |

## What was completed

WBS 3.4 closes work area 3 except for Safe Browsing in 3.5. Every endpoint in
the approved design now exists: /health, /register, /scan and /feedback.

`/register` issues one token per installation — 32 bytes from a CSPRNG, returned
once, stored only as a SHA-256 hash. This is the implementation of the A-02
design that answered the grader's objection to the original proposal. The thing
worth restating is what the token is not: it is not proof of identity, and
anyone can call /register and obtain one. What it buys is isolation and
revocability. One installation can be rate limited or cut off without affecting
any other, which a single shared key baked into the extension could never do.

Rate limiting followed: 60 scans a minute per install, 20 feedback submissions
an hour per install, and 10 registrations an hour per source IP. The registration
limit is the tightest because that endpoint is where identities are minted, and
per-identity limits mean nothing if identities are free.

`/feedback` records a user disagreeing with a verdict. Three rules shape it.
Authentication is required with no degraded path, because unattributable
feedback cannot be weighted or isolated if it turns out to be poisoned. A caller
may only leave feedback on its own scans, or the endpoint becomes a way to probe
which scan ids exist. And feedback is never applied to the model automatically —
it lands for human review, because a system that retrains itself on complaints
can be argued out of its own judgement by whoever complains most.

WBS 4.1 built the extension scaffold: manifest, permissions, the service worker
that owns the install token, and the content script that mounts a shadow-root
host on the open message. The token deliberately lives in the service worker
rather than the content script. The content script runs inside Gmail's page,
alongside a great deal of code not under my control; the worker does not.

A-19 produced the interface mockups. The first attempt was a styled design sheet
and was discarded — a mockup exists to show what the thing will actually look
like, so the second version is a literal rendering at real size. Drawing it
forced four decisions that would otherwise have surfaced mid-build: what the
panel shows while waiting, when rate limited, when the API is unreachable, and
when a scan succeeded but could not be recorded. The unreachable state got the
most attention, because silence reads to a user as "this message is fine."

## Decisions recorded against the proposal

Two, both in the change log.

The first is a question the approved design did not answer: what should /scan do
when the database holding the tokens is unreachable? It cannot verify a token in
that state. It now scores the message anyway and records nothing, reporting
`persisted: false`. A phishing warning withheld because a database is offline is
the worse failure, and the scoring endpoint holds no secrets, bounds every field,
and still applies a per-IP rate limit. Feedback does not degrade the same way —
it is refused outright, because feedback nobody can attribute is worth nothing.

The second is smaller. Rate limiting was built on the `limits` library rather
than `slowapi`, which the proposal's dependency list named. slowapi's route
decorator rewrites the handler signature, after which FastAPI stopped recognising
request bodies and every /scan returned 422. limits is slowapi's own engine, so
the behaviour is identical; it is applied as a dependency instead.

## What went wrong

WBS 5.2 was carried as in progress when it was actually blocked. The Docker stack
has been running on the droplet since 28 October, but Nginx and TLS cannot be
finished because Let's Encrypt will not issue a certificate for a bare IP
address, and the hostname depends on a GitHub Student Pack application pending
since September. Carrying it as in progress made the schedule look healthier than
it was. It is now marked blocked with the dependency written down.

A test I wrote this week was itself broken — it only imported when pytest ran
from inside `03_Backend`, because import sorting had moved a line above the one
that registers the package. It was found while counting tests for the weekly
update, which is a reasonable argument for the weekly update being more than
paperwork. The suite now runs from either directory: 94 tests passing, up from 75.
