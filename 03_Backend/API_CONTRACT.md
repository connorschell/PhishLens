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

## CORS

Empty allowlist means same-origin only. The deployed `.env` sets
`ALLOWED_ORIGINS=["chrome-extension://<id>"]` once WBS 4.1 has a published id.
