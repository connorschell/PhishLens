# Extension-to-API Authentication — Revised Design

**Grader item A-02.** Response to feedback on the approved project proposal.
Connor Schell · CYBR 498W · PhishLens · 2026-09-30

---

## The problem with the approved design

The proposal specified a single extension-scoped API key, compiled into the
extension and sent with every request to the scoring service.

A Chrome extension cannot keep a secret. Everything the extension ships —
`manifest.json`, the content script, the service worker — is plain text on the
user's disk under `chrome-extension://`, and anyone can unpack a `.crx` or read
the unpacked directory. Obfuscation only changes how long extraction takes.

A shared key that cannot be kept secret has three consequences that matter here:

1. **Anyone can call the API.** One extracted key authenticates the whole user
   base, so there is no rate limit that constrains an abuser without also
   constraining every legitimate install.
2. **Nothing can be revoked.** Cutting off an abuser means rotating the key,
   which breaks every installation until each one updates.
3. **Nothing can be attributed.** Feedback submitted to `/feedback` (WBS 3.4) and
   scan history in the dashboard (WBS 4.5) cannot be tied to an install, so
   feedback cannot be rate-limited or weighted, and poisoned feedback cannot be
   isolated.

## The revised design

Replace the shared static key with a **per-install token issued by the server at
first run**, and treat that token as an *identifier*, not as a secret.

### Registration

On first run, the extension's service worker calls:

```
POST /register
Content-Type: application/json

{ "extension_version": "0.1.0", "client_platform": "chrome" }
```

The server generates 32 bytes from a CSPRNG, stores a SHA-256 hash of the token
alongside an install id, and returns the token once:

```
201 Created
{ "install_id": "e3b0c442...", "token": "pl_live_9f2c...", "issued_at": "..." }
```

The extension stores the token in `chrome.storage.local`, which is scoped to the
extension's origin and not readable by page scripts, including Gmail's.

### Authenticated requests

```
POST /scan
Authorization: Bearer pl_live_9f2c...
```

The server hashes the presented token and looks it up. Only the hash is stored,
so a database disclosure does not yield usable tokens.

### Why this is honest about its own limits

A per-install token issued to an anonymous client is not proof of identity. A
determined attacker can call `/register` repeatedly and mint as many tokens as
they like. What the design buys is not unforgeability — it is **isolation and
revocability**:

| Property | Static shared key | Per-install token |
|---|---|---|
| Recoverable from the shipped extension | Yes | The token is generated at runtime, not shipped |
| Rate limiting granularity | Whole user base | One install |
| Revocation blast radius | Every install | One install |
| Feedback attribution | None | Per install |
| Cost of abuse at scale | One extraction | One `/register` call per identity, each independently rate-limited and revocable |

Mass registration is handled as its own problem: `/register` is rate-limited by
source IP, and an install id that trips the `/scan` limit or submits feedback
that disagrees with the model far outside the population norm is flagged and can
be revoked without affecting anyone else.

### What is explicitly *not* claimed

- This is not user authentication. PhishLens has no user accounts and asks for no
  credentials. The token identifies an installation, not a person.
- This is not a defence against a hostile client. A client that wants to send
  fabricated feature payloads can do so. The server therefore validates and
  bounds every field of the payload rather than trusting the client's framing,
  and feedback is treated as a signal to review, never as ground truth applied
  automatically to the model.
- No API key for a third-party service is ever placed in the extension. The
  Google Safe Browsing key (WBS 3.5) lives only in the server's environment; the
  extension never contacts Google directly.

## Server-side controls that go with it

| Control | Where it is built | Notes |
|---|---|---|
| Token hashing at rest (SHA-256) | WBS 3.4, `app/auth.py` | Plaintext token returned once, never stored |
| Per-install rate limit on `/scan` | WBS 3.4 | Sliding window; exceeding it returns 429, not a ban |
| Stricter per-IP rate limit on `/register` | WBS 3.4 | Bounds mass minting |
| Revocation flag on the install record | WBS 3.1 schema | Revoked token returns 401 immediately |
| CORS restricted to the extension origin | WBS 3.3 | `chrome-extension://<id>` only |
| TLS everywhere | WBS 5.2 | Nginx + Let's Encrypt; HTTP redirects to HTTPS |
| Payload bounds validation | WBS 3.3 | Pydantic models cap field lengths and list sizes |

## Database impact

The schema in WBS 3.1 gains an `installs` table:

| Column | Type | Note |
|---|---|---|
| `install_id` | uuid, PK | |
| `token_hash` | bytea, unique, indexed | SHA-256 of the issued token |
| `extension_version` | text | |
| `created_at` | timestamptz | |
| `last_seen_at` | timestamptz | |
| `revoked_at` | timestamptz, null | Non-null means every request is rejected |

`scans` and `feedback` both gain a `install_id` foreign key, which is what makes
per-install rate limiting and feedback attribution possible.

## Schedule impact

WBS 3.4 grows from 6 to 7 hours to add the `/register` endpoint and the token
issuance and hashing path. No other task changes, and no milestone moves.
Recorded as Change Log entry #1 and reported in Weekly Update #2.

## Status

Design settled 2026-09-29. Implementation lands in WBS 3.4 (week of 11/4)
alongside `/feedback` and rate limiting, on the schema created in WBS 3.1.
