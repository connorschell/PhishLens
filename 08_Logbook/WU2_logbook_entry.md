# Logbook — Week 2 (WU2)

**Connor Schell · CYBR 498W · PhishLens**
Week ending 2026-09-30 · Weekly Update #2 · **12.0 hours this week**

---

## 2026-09-29 — Proposal feedback and re-planning (4.0 hrs)

**A-02 · 1.5 hrs.** Read Dr. Almalag's feedback on the approved proposal and
pulled out the two open items: Table of Contents page numbers, and the
extension-to-API authentication design. Worked the auth problem: a Chrome
extension ships its entire source in plain text, so the single static API key in
the proposal can be extracted from any install and cannot be rate-limited,
revoked, or attributed. Settled on per-install tokens issued by a `/register`
endpoint at first run, stored hashed server-side, treated as an identifier rather
than a secret.

**A-17 · 1.0 hr.** Built the purchases and accounts list and checked costs:
GitHub Student Developer Pack (free domain, hosting credit), domain registrar,
VPS sizing, Google Safe Browsing key, Chrome Web Store decision, throwaway Gmail
accounts for end-to-end testing. Total expected spend $0–39.

**A-03 · 0.5 hr.** Re-sequenced the schedule so IM1 stays on track: 1.1 and 1.2
move into this week, 1.3–1.5 into WU3, and the baseline classifier into the
week of 10/12, which has no weekly update because of fall break.

**A-03 · 1.0 hr.** Rebuilt the project tracker to match the approved proposal:
task register with 44 tasks across the six WBS areas, time log, deliverables,
change log, and weekly update tabs.

## 2026-09-30 — Repository scaffold and corpus pipeline (8.0 hrs)

**A-02 · 0.5 hr.** Wrote up the authentication design as
`00_Admin/auth-design-revision.md`: the failure modes of the approved design,
the `/register` flow, the database changes it forces (an `installs` table, and
`install_id` foreign keys on `scans` and `feedback`), the server-side controls
that go with it, and an explicit section on what the design does *not* claim.
It does not make the client trustworthy — it makes abuse isolatable and
revocable. Grader item A-02 closed. WBS 3.4 grows 6 → 7 hours.

**A-17 · 0.5 hr.** Wrote up the purchases list as
`00_Admin/purchases_and_accounts.md` with a per-item owner and status, and a
recommendation not to pay for a Chrome Web Store developer account — both demos
work with the extension loaded unpacked, and a store review could land after the
demo date. Accounts themselves are still mine to create.

**1.2 · 3.0 hrs.** Scaffolded the repository. Pinned Python 3.11 with FastAPI,
PostgreSQL 16, and scikit-learn in `requirements.txt`. Wrote a Dockerfile that
builds a non-root image with a healthcheck, and a Compose stack for the API and
database with both ports bound to loopback only. Directory layout mirrors the
proposal WBS. Added `.env.example`, ruff and pytest config, a README, and a
`/health` stub so the stack can be brought up and verified before WBS 3.3 adds
real endpoints. Initialized git and committed.

**1.1 · 4.0 hrs.** Built the corpus pipeline. Hit the first real obstacle
immediately: neither `spamassassin.apache.org` nor `monkey.org` is reachable from
my build network, so neither corpus named in the proposal could be downloaded
directly. Found the SpamAssassin corpus intact on a GitHub mirror — same groups,
same counts, raw message text preserved — and replaced the Nazario collection
with Phishing Pot, a honeypot corpus of real phishing from 2022 onward in `.eml`
with headers intact. That substitution is an improvement on its own terms: WA#3
named stale corpora as a project risk, and Nazario's newest samples are from
2017.

Wrote `acquire_corpus.py`, which caches shallow clones outside the project and
writes one compressed archive per corpus into `01_Data/raw/` along with a
manifest recording each source's commit hash — so any number in the final report
traces back to a specific version of a specific corpus. Archives rather than
loose files because the project folder is in OneDrive and 29,000 small files
would leave the sync client churning all semester.

Wrote `record_schema.py` — the common record every message becomes, and the same
shape the extension will send from the Gmail DOM in WBS 4.2. Three fields are
marked corpus-only (`Received` count, `Return-Path`, `Authentication-Results`),
because the Gmail DOM does not expose them and the model must not learn from
signals it will not have at inference time.

Wrote `normalize.py`, which streams both archives into that schema: sender
address, domain and registered domain; `Reply-To`/`Return-Path` mismatch;
subject, date, `Message-ID`; body text with HTML stripped; every link with its
registered domain and anchor text, flagged where the anchor names a different
domain than the href; attachment metadata without touching payloads.

De-duplication was the part that mattered most. Exact-byte matching removed only
5 messages. Near-duplicate matching — sender domain plus subject plus the first
800 characters of body, with digits and hex runs masked — removed 1,954,
including **1,788 phishing messages, 21% of that class**. Those are single
campaigns blasted repeatedly with rotating tracking IDs. Left in, they would have
landed on both sides of the train/test split and made the classifier look far
better than it is.

Result: 12,700 records from 14,659 read — 6,820 phish, 4,091 ham, 1,789 spam.
Documented in `01_Data/CORPUS.md`, including the class-balance caveat: phishing
is 54% of this corpus and nothing like that in a real inbox, so precision and
false-positive rate have to be read against a realistic prior. Spam is kept as a
third label rather than folded into ham, because unsolicited bulk mail is the
hardest negative class and the main source of false positives this project has to
survive.

Two engineering problems worth recording. First, my build shell kills background
jobs when the call that started them ends, so a full normalization run kept dying
partway; I added `--only` and `--append` flags with de-duplication state
persisted between runs, so the pipeline can be built up in slices. Second, git
could not create lock files in the project folder until file deletion was
enabled for it.

---

## Open at the end of the week

- **A-01 (TOC page numbers) — blocked.** `Schell_Connor_Project_Proposal.docx` is
  not in the capstone folder. It needs to be put there before the TOC can be
  regenerated. This is the one grader item still open.
- **A-17 — partly open.** The plan and the write-up are done; creating the
  accounts and claiming the domain are mine to do.
- **A-03 — in-class standup** still to be delivered.

## Next week (WU3, due 2026-10-07)

1.3 email parser (6 hrs), 1.4 feature extractor (8 hrs), 1.5 labeled dataset,
train/test split, and feature dictionary (4 hrs), plus A-04 Weekly Update #3.
