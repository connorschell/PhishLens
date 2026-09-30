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
cp .env.example .env          # then edit the passwords
docker compose up --build     # API on 127.0.0.1:8000, Postgres on 127.0.0.1:5432
curl http://localhost:8000/health
```

Without Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
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
