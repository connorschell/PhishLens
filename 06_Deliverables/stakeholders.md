# Stakeholder Identification

**PhishLens — explainable AI-assisted phishing detection for the Gmail web client**
Connor Schell · CYBR 498W · Dr. Mohammad Almalag · Deliverable #3 · drafted for IM1

---

## Scope of this document

Analysis asks who will use the system, whether there is more than one type of
user, and what characterizes them. This document answers that, and records one
thing the answer depends on: **PhishLens has no user accounts.** It asks for no
credentials, stores no email address, and never learns who a user is. The
per-install token issued by `/register` identifies an *installation*, not a
person (`00_Admin/auth-design-revision.md`).

Stakeholder types are therefore distinguished by **what they are able to change
in the system**, not by a role field in a database. There is no login screen to
separate them; separation is by surface — the extension panel, the dashboard,
and the command line.

---

## 1. Message Recipient — the primary user

The person reading a message in the Gmail web client in Chrome with the
extension installed.

**Characteristics**

- Not a security specialist. Cannot be assumed to know what SPF, DKIM, a
  registrable domain or a homoglyph is. Every signal shown must survive being
  read by someone who knows none of those words.
- Reading mail as an interruption to other work. The verdict competes with the
  user's intention to open the message, so it has to arrive before the decision
  is made, not after. Measured scan latency is 83 ms locally; the panel must not
  make the user wait on a round trip they notice.
- Acting under the same pressure the message is engineered to create. Urgency is
  a phishing feature, which means the explanation has to be readable fast.
- Already conditioned by spam filters to ignore warnings. A banner that is wrong
  often enough gets dismissed reflexively, which is why this is a system of
  severity tiers (`clear`, `caution`, `suspicious`, `dangerous`) rather than a
  binary verdict, and why false-positive rate is a reported metric.
- Has an opinion the system does not have: the recipient usually knows whether
  they were expecting the message. The system does not, and cannot.

**What they change in the system**

- Each scored message writes one `scans` row and its `indicators` rows.
- Disagreeing with a verdict writes a `feedback` row (one per install per scan).

**What they cannot do**

Retrain the model, see anyone else's scans, or change a severity threshold.

---

## 2. Dashboard Reviewer

Operates the web dashboard (WBS 4.5): scan history, the feedback queue, and
model performance over time. In this project that is the developer; in a
deployed setting it would be whoever runs the instance — a security-aware
administrator, not necessarily the person who built it.

**Characteristics**

- Works after the fact, in aggregate, across installs — the opposite of the
  recipient's single-message, immediate view.
- Needs to know *which model* produced a result. A verdict read three weeks
  later is uninterpretable without the version that produced it, which is why
  every scan carries a `model_version_id`.
- Cannot inspect the message behind a scan, by design. Review works from the 43
  measurements, the score and the stored explanation; the subject, body and
  sender were never stored (`00_Admin/data-handling.md`). This is a real
  constraint on this user, accepted deliberately.

**What they change in the system**

- Sets `feedback.reviewed_at` when a report has been triaged.

**What they cannot do**

Promote a model, or let feedback alter a verdict. Feedback is a signal to
review, never ground truth applied automatically.

---

## 3. Model Maintainer

Trains, evaluates and promotes models. The command-line user: `train_baseline.py`,
`evaluate.py`, `build_dataset.py`.

**Characteristics**

- The only stakeholder who sees the corpora and the training pipeline.
- Bound to report precision, recall and false-positive rate — never accuracy —
  and to report them twice, full and ablated, because six features showed
  single-feature AUC high enough to be era proxies rather than phishing signal.
- Responsible for the calibration the recipient experiences as trust: severity
  thresholds live in `model_versions.severity_tiers`, so a tier change is a
  versioned act, not an edit.

**What they change in the system**

- Inserts `model_versions` rows; flips `is_active` (a unique index enforces
  exactly one active model).

---

## 4. Evaluator — Dr. Almalag

Installs the extension, runs it against seeded messages in a test Gmail account,
and reads the deliverables.

**Characteristics**

- Arrives with no prior context from inside the project and uses only what is
  written down. Install instructions, the live URL and the README are this
  user's entire interface.
- Needs the claims to be checkable: the evaluation numbers, the repository
  history and the running system have to agree with each other.

Treated here as a real user type rather than an audience, because the
installation path is a requirement that exists only for this stakeholder.

---

## Indirect stakeholders — affected, but not users

| Stakeholder | Interest | How the design answers it |
|---|---|---|
| **Senders of legitimate bulk mail** (retailers, SaaS notifications, university mailings) | A false positive damages a sender who did nothing wrong. Their mail legitimately carries brand/domain mismatch, urgency language and click-tracking redirectors — the same features phishing carries. | False-positive rate is a reported metric; WBS 2.4 calibrates severity against legitimate bulk mail specifically; tiers let a borderline message read as `caution` instead of an accusation. |
| **Google — Gmail web client** | The extension parses rendered Gmail DOM. No Gmail API, no OAuth, no account access. | Content script reads only the open message; a Gmail UI change breaks parsing, which is a tracked risk, not a surprise. |
| **Google Safe Browsing** | External dependency with a quota and an availability profile the project does not control. | One weighted input among many, locally cached by URL hash, with graceful degradation — a stale or missing cache row means the signal is simply unused for that scan. |
| **CNU / the course** | Owns the grading criteria and the deliverable list. | Deliverables register in the tracker maps every artifact to a due date. |

---

## Future users, if the project continued past the semester

- **A small organization's IT administrator**, wanting one dashboard across many
  installs. The schema already supports this — scans and feedback carry
  `install_id` — but nothing enforces a tenancy boundary, so this would require
  real authentication, which the current design explicitly does not claim to
  provide.
- **A privacy-constrained recipient** whose mail may not leave the browser. The
  follow-on work is client-side feature extraction; the blocker is maintaining
  43 measurements in two languages without drift, not the design.
- **Non-Gmail webmail users.** The parser is shared between corpus `.eml` files
  and the DOM scrape, so a second client needs a new scraper, not a new model.

---

## Summary

| Stakeholder | Surface | Writes | Primary need |
|---|---|---|---|
| Message Recipient | Extension panel in Gmail | `scans`, `indicators`, `feedback` | A verdict they can check for themselves, fast |
| Dashboard Reviewer | Web dashboard | `feedback.reviewed_at` | To see whether the system is behaving across many scans |
| Model Maintainer | Command line | `model_versions` | Honest metrics and a reversible promotion |
| Evaluator | Install + live URL | — | To reproduce the claims without the author present |
