# Week 5 logbook entry — week ending 28 October 2026

PhishLens · CYBR 498W · Connor Schell

## Hours

15 hours on 21 October, against 18.5 hours estimated for the WBS 3 tasks
scheduled this week. Closer to estimate than weeks 3 and 4, which ran well under:
the parser and feature extractor built in week 3 meant the scoring service was
wiring rather than writing, but the schema and the endpoint behaviour under
failure took longer than the carry-forward suggested they would. Running total
58 hours.

| Task | Hours | What was done |
|---|---|---|
| 3.1 | 5.5 | Schema design — six tables, privacy decision bound into the schema |
| 3.2 | 2.5 | PostgreSQL implementation, migrations, seed scripts |
| 3.3 | 7.0 | /scan and /health endpoints wired to model and explanation engine |

## What was completed

WBS 3.1, 3.2 and 3.3 are done. Work area 3 is complete except 3.4 (feedback,
token auth, rate limiting) in week 6 and 3.5 (Safe Browsing) in week 8. Eleven of
twenty-five WBS subtasks are now complete, a week ahead of the proposal calendar.

The schema is six tables: installs, model_versions, scans, indicators,
url_reputation and feedback. Two design decisions are bound into it rather than
left to discipline.

First, no message content is stored. The scans table has no column able to hold a
subject, body or sender address, so storing one would require a migration — a
visible act rather than a quiet one. A salted SHA-256 fingerprint over the
normalised subject and body makes a re-scan recognisable without the message
being recoverable from the row. The reasoning, including why client-side feature
extraction was rejected for now, is written up in 00_Admin/data-handling.md.

Second, every scan records the model version that produced it, and a unique index
permits exactly one active model. Without this, a result read in the dashboard
three weeks later cannot be attributed, and the full-versus-ablated comparison
from week 4 becomes unreportable.

The installs table carries the authentication design rewritten after the proposal
feedback: token_hash is a 32-byte digest, never the token, with a revoked_at
column so one installation can be cut off without affecting any other.

/scan and /health are built on top of this. The scoring service calls
parse_email, features, contributions and explain — the same four modules the
milestone demo calls, in the same order — and a test asserts the API response
equals a direct call to the model field for field, including the order of the
explanation sentences. There is no second implementation anywhere in the scoring
path, which is the arrangement week 3 was built to guarantee.

Persistence is deliberately off the critical path. If the database is unreachable
the verdict and explanation are still returned, with persisted = false and a null
scan id. Withholding a phishing warning to protect a history feature is the wrong
trade. /health reports model and database separately so a failure cannot hide
behind a single ok.

Every inbound field is bounded by a Pydantic model, per the authentication
revision: the extension is a client the server does not control, so the server
validates rather than trusts.

Measured 83 milliseconds per scan locally. A live payload scored 98 out of 100,
with the rule layer correctly catching a link whose text reads ledger.com and
whose destination is elsewhere. Eight new tests; the repository suite is now 75,
all passing.

## Changes against the proposal

One, recorded as Change Log #13. The extension sends the message and the server
parses it, rather than the extension extracting the 43 measurements and sending
only numbers. The stronger privacy position would require a second implementation
of the parser and all 43 measurements in JavaScript, kept in exact step with the
Python used for training; drift between the two produces a model scoring inputs
that are subtly not the inputs it was trained on, which is the same class of
defect the week 3 review caught and the hardest to notice. The bound placed on
storage — no message content, enforced by the absence of columns — recovers most
of the privacy benefit without that risk. No schedule impact. Client-side
extraction is named as the first use of the reserve period if the project
finishes ahead.

## Carried into week 6

- WBS 3.4: /feedback, per-install token registration, rate limiting. 7 hours.
- WBS 5.1 VPS provisioning and hardening, sequenced first within the week, ahead
  of 3.4. It is the only remaining task with external dependencies - domain,
  hosting account, DNS, certificate - and the server must be live with a valid
  certificate for the second milestone demo on 9 November. 3.4 is code that can
  be written at any point in the week.
- WBS 5.2: Docker Compose and Nginx with Let's Encrypt TLS. 5 hours.
- Outstanding accounts: domain, Google Safe Browsing key, two test Gmail accounts.
- A-01, the proposal table of contents, still blocked on the approved document.

## Risk

The GitHub Student Developer Pack has been pending review since 30 September. The
hosting credit and free domain for WBS 5.1 depend on it. If it has not cleared by
the end of week 6 I will pay for a basic server rather than let the milestone demo
wait on a third party.
