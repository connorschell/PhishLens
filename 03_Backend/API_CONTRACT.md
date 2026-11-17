# PhishLens API contract

**WBS 3.4 · v0.3.0 · 2026-11-02.** Generated schema: `03_Backend/openapi.json`
(regenerate with `python -c "import json;from app.main import app;print(json.dumps(app.openapi()))"`).
This file is what WBS 4.1/4.2 build against; if the two disagree, the generated
schema wins.

## Endpoints

| Method | Path | Auth | Limit | Purpose |
|---|---|---|---|---|
| `GET`  | `/health`   | none | none | Model and database reported separately |
| `POST` | `/register` | none | 10/hour per IP | Mint one per-install token |
| `POST` | `/scan`     | Bearer | 60/min per install | Score a message, return the panel |
| `POST` | `/feedback` | Bearer | 20/hour per install | Record disagreement with a verdict |
| `POST` | `/dashboard/api/login` | password | 10/hour per IP | Exchange the operator password for a session |
| `GET`  | `/dashboard/api/scans` | Dashboard session | none | Paged scan history across installs |
| `GET`  | `/dashboard/api/feedback` | Dashboard session | none | Feedback queue, newest and unreviewed first |
| `POST` | `/dashboard/api/feedback/{id}/review` | Dashboard session | none | Stamp `reviewed_at` |
| `GET`  | `/dashboard/api/metrics` | Dashboard session | none | Operational counts |

## First run

```http
POST /register
{ "extension_version": "0.1.0", "client_platform": "chrome" }

201 { "install_id": "...", "token": "pl_live_...", "issued_at": "..." }
```

The token is returned once. The service worker stores it in
`chrome.storage.local` and sends it as `Authorization: Bearer <token>` on every
later call. Only its SHA-256 hash is stored server side. A `503` here means the
token store is unreachable — retry with backoff, do not fall back to scanning
unauthenticated, and do not invent a token.

## Scanning

`POST /scan` takes the scraped message (`from_display`, `from_address`,
`reply_to_address`, `subject`, `body_text`, `body_html`, `attachments[]`) and
returns the full panel: `risk_score`, `severity`, `headline`, `advice`,
`signals[]`, `mitigating[]`, `model_severity`, `severity_floored_by`,
`scan_id`, `persisted`, `duration_ms`.

`scan_id` is what `/feedback` refers to. It is `null` when the scan was not
recorded (`persisted: false`); the feedback control must be hidden in that case
rather than posting an id it does not have.

## Feedback

```http
POST /feedback
Authorization: Bearer pl_live_...
{ "scan_id": 1234, "disagreement": "false_positive", "note": "optional, <=500 chars" }
```

An install may only leave feedback on its own scans, and only once per scan.

## Status codes the extension must handle

| Code | Meaning | Client behaviour |
|---|---|---|
| `401` | Missing, unrecognised or revoked token | Re-register once; if it fails again, show the panel as unavailable |
| `403` | That scan belongs to another install | Bug in the client; do not retry |
| `404` | No such scan | Drop the feedback control |
| `409` | Feedback already left on that scan | Treat as success |
| `422` | Payload out of bounds | Bug in the client; do not retry |
| `429` | Rate limit | Back off for `Retry-After` seconds |
| `503` | Model or token store unavailable | Retry with backoff |

## Degraded behaviour

The installs table is the token store, so when the database is unreachable the
server cannot verify a presented token. `/scan` then scores the message anyway
and records nothing (`persisted: false`); withholding a phishing warning over a
database outage is the worse failure. `/register` and `/feedback` do not
degrade: an unverifiable token and unattributable feedback are both worse than
a clear `503`. Full reasoning in `app/auth.py` and
`00_Admin/auth-design-revision.md`.

## Dashboard (WBS 4.5)

Two different credentials, deliberately. The per-install bearer token is scoped
to one install's own rows; the dashboard reads across all of them, so it has its
own operator password set in the deployed `.env`:

```http
POST /dashboard/api/login
{ "password": "..." }

200 { "token": "pl_dash_...", "expires_at": "..." }
```

The password is checked once and exchanged for a session token — an HMAC over
its own expiry, keyed by `TOKEN_SIGNING_SECRET`, stateless and valid for
`DASHBOARD_SESSION_HOURS` (default 12). Sent as `Authorization: Bearer` on every
dashboard call. An install token presented here is rejected; so is a dashboard
session presented to `/scan`.

Fail-closed: with `DASHBOARD_PASSWORD` or `TOKEN_SIGNING_SECRET` unset — or the
signing secret still at the `change_me_locally` placeholder — login and every
dashboard route return `503`. A deployment that forgot to set the password gets
a dashboard that does not work rather than one serving scan history publicly.

Rotating `TOKEN_SIGNING_SECRET` and restarting invalidates every outstanding
session. That is the only revocation this stateless scheme has, and it is
deliberate for a single-operator deployment.

Unlike `/scan`, these routes have no degraded path: a dashboard is a convenience
and an honest `503` beats a page that looks authoritative while showing nothing.

The page itself is served at `/dashboard/` from
`03_Backend/app/static/dashboard/`.

## CORS

Empty allowlist means same-origin only. The deployed `.env` sets
`ALLOWED_ORIGINS=["chrome-extension://<id>"]` once WBS 4.1 has a published id.
