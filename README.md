# PhishLens

Explainable AI-assisted phishing detection for the Gmail web client.
CNU CYBR 498W capstone, Fall 2026 — Connor Schell.

A Chrome MV3 extension reads the open Gmail message from the page DOM, sends
extracted features to a hosted API, and displays a risk score, a severity tier,
and a ranked plain-English list of the signals that produced it. Explainability
is the defining feature, not raw detection rate.

## Repository layout

Directories are numbered to match the WBS in the approved proposal.

| Path | WBS | Contents |
|---|---|---|
| `00_Admin/` | — | Design notes, grader-item responses, purchases and accounts |
| `01_Data/` | 1 | Corpus acquisition, parser, feature extractor, splits |
| `02_Model/` | 2 | Classifier training, evaluation, contributions, explanations |
| `03_Backend/` | 3 | FastAPI service, routes, services, PostgreSQL schema and migrations |
| `04_Extension/` | 4 | MV3 extension and web dashboard |
| `05_Deployment/` | 5 | VPS provisioning, Docker Compose, Nginx, backups, test plan |
| `06_Deliverables/` | — | Presentations, reports, design artifacts |
| `07_WeeklyUpdates/` | — | Weekly update submissions |
| `08_Logbook/` | — | Cumulative logbook |
| `09_Reference/` | — | Source material and reference documents |

`PhishLens_Capstone_Tracker.xlsx` is the plan of record: task register, time log,
deliverables, change log, and weekly updates.

## Stack

Python 3.11 · FastAPI · PostgreSQL 16 · scikit-learn · Docker Compose ·
Nginx + Let's Encrypt (production) · Chrome Manifest V3.

One language across the data pipeline, model, and API. FastAPI generates the
OpenAPI schema that defines the extension-to-API contract.

## Local development

```bash
cp .env.example .env          # then edit the passwords and the fingerprint salt
docker compose up --build     # API on 127.0.0.1:8000, Postgres on 127.0.0.1:5432
curl http://localhost:8000/health

# register the trained model so /scan has something to score with
docker compose exec api python 03_Backend/db/seed/seed_model_version.py --variant full --activate
docker compose exec -T db psql -U phishlens -d phishlens < 03_Backend/db/seed/seed_dev_install.sql

# every install gets its own token (WBS 3.4); /scan requires one
TOKEN=$(curl -s -X POST http://localhost:8000/register \
  -H 'content-type: application/json' \
  -d '{"extension_version":"0.2.0","client_platform":"chrome"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["token"])')

curl -X POST http://localhost:8000/scan \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"from_display":"LEDGER","subject":"Verify your account","body_text":"Confirm your password","body_html":"<a href=\"https://x.example\">https://www.ledger.com</a>"}'

# without a token, the same request is rejected
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/scan \
  -H 'content-type: application/json' -d '{}'      # 401
```

The database schema is created automatically on the first start of the database
volume from `03_Backend/db/migrations/`. `03_Backend/db/schema.sql` is the
annotated reference copy.

### What the API stores

Message content is never written to the database. A scan row holds the 43
measurements, the score, the severity tier and the explanation, plus a salted
fingerprint so a repeat scan is recognisable without the message being
recoverable. The reasoning is in `00_Admin/data-handling.md`.

Without Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## The Chrome extension

Manifest V3, in `04_Extension/`. It reads the open message from the Gmail page,
sends it to the API, and renders the score, the severity tier and the ranked
explanation in a panel above the message body.

```
chrome://extensions  ->  Developer mode  ->  Load unpacked  ->  04_Extension
```

`config.js` points at `http://localhost:8000` by default. Chrome treats
`http://localhost` as a trustworthy origin, so the extension works against a
locally running stack with no certificate; the deployed server requires HTTPS
and is pending a hostname (WBS 5.2).

| File | Role |
|---|---|
| `manifest.json` | Permissions, content-script registration, CSP |
| `config.js` | API address, storage keys, timeouts, backoff — the only constants |
| `background/service_worker.js` | Registration, token custody, every API call |
| `content/parse.js` | Reads the message out of the Gmail DOM (the fragile file) |
| `content/panel.js` | Renders the verdict and every non-verdict state |
| `content/gmail.js` | Decides when to scan; mounts and tears down the panel |

The install token never reaches the content script. The content script posts a
message to the service worker, the worker attaches `Authorization: Bearer`, and
only the panel data comes back — so the code running inside Google's page never
holds the credential.

Endpoint reference: `03_Backend/API_CONTRACT.md` and `03_Backend/openapi.json`.

## Tests

```bash
python -m pytest 01_Data 02_Model 03_Backend      # 94 tests
```

## Data

Corpora are not committed. `01_Data/src/acquire_corpus.py` downloads them and
`01_Data/src/normalize.py` converts them to a common record schema.
See `01_Data/CORPUS.md` for sources, licences, and counts.

## Constraints carried from the approved proposal

- Chrome MV3 extension parsing the Gmail web DOM. No Gmail API, no OAuth.
- Explanations derive from real per-feature model contributions plus a
  deterministic rule layer. No LLM in the scoring path.
- Google Safe Browsing is one weighted, cached input with graceful degradation.
- Evaluation reports precision, recall, and false-positive rate — never accuracy.
- Verdicts are severity tiers, not binary.
- No client-side secret. Per-install tokens issued by `/register`
  (see `00_Admin/auth-design-revision.md`).
