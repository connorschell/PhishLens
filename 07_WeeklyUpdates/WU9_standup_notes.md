# WU9 standup notes — Monday 23 November

Personal prep. Not a deliverable, not submitted.

---

## The 30-second version

If you only get one breath: *Backups are done and verified. The test plan is
written. And I found out this week that my model has been separating old email
from new email rather than phishing from legitimate mail, so the calibration
task is now blocked behind rebuilding the training data with my own modern
inbox.*

That last sentence is the one that matters. Lead with it if he asks what's
going on, not with the backups.

---

## Item 1 — Database backups (WBS 5.3) — DONE

**Say:** "I set up automatic nightly backups of the database on the server, plus
a script that restores a backup into a throwaway copy and checks the data came
back intact. It runs weekly on its own. The first two times I ran the check it
failed, and both times the bug was in my checking script, not the backups. Third
run passed clean."

**Proof to pull up:**

```bash
systemctl list-timers 'phishlens-*'                  # both timers scheduled
ls -lh /var/backups/phishlens/                       # dumps on disk
journalctl -u phishlens-backup.service -n 10 --no-pager
./05_Deployment/backup/restore_test.sh               # runs in ~5 seconds, ends PASSED
```

Running the restore test live is the strongest thing you can do. It takes
seconds and ends with `RESTORE TEST PASSED`.

**Files:** `05_Deployment/backup/` — `backup.sh`, `restore_test.sh`, two systemd
service/timer pairs, `README.md`.

**Numbers to know:** six tables restored, five foreign keys, exact row parity —
143 scans, 283 indicators, 8 installs, 9 cached URLs, 4 feedback rows; the join
returned 313 rows. Nightly at 03:12 UTC, 7 daily + 4 weekly kept.

---

## Item 2 — End-to-end test plan (WBS 5.4) — WRITTEN, NOT RUN

**Say:** "I wrote a test plan that covers the whole system end to end — 31 tests
across the extension, the server and the database. One group is cases I already
know fail today, which I put in deliberately so the plan can't pass while the
product doesn't. I haven't run it yet; that's this week."

**Proof:** `05_Deployment/test_plan_and_results.md`. Scroll to Group D if he
wants to see the honest part.

**Numbers:** 31 cases, six groups. Groups A–C and E–F are expected to pass;
Group D (3 cases) is expected to fail until 2.4.

---

## Item 3 — Training data groundwork (WBS 1.6) — GROUNDWORK ONLY

**Say:** "I wrote the code that reads an export of my own Gmail into the
training data, and documented the privacy side — what gets exported, what leaves
the machine, and the fact that other people wrote those messages and didn't
consent to being in a training set. I haven't done the actual export yet."

**Proof:**
- `01_Data/CORPUS.md` → the "Personal legitimate mail (WBS 1.6)" section
- `01_Data/src/normalize.py` → `read_personal_ham()`

**The honest line if pressed:** nothing leaves the machine. The files that get
used downstream carry a record ID, a label, and 43 numbers per message — no
subject, no body, no addresses.

---

## Item 4 — The finding (why 2.4 is blocked) — THE IMPORTANT ONE

**Say:** "My legitimate training emails are from 2002 and my phishing samples
are from 2022 onward. So the model has partly been learning to tell old mail
from new mail instead of phishing from legitimate. The clearest example is plain
http links — they show up in 80% of the old legitimate messages and only 37% of
the phishing, so the model learned that an http link means safe. Modern mail is
https everywhere, so modern legitimate mail gets scored as unsafe. I tested that
by rescoring the 818 legitimate test messages with just that one feature flipped
to https, and the share flagged for caution went from 11.9% to 59.2%."

**Then the consequence:** "No threshold change fixes that, and I can't even
measure it properly with my current test set, because the test set has the same
age gap built into it. So I need modern legitimate mail first. That's why 1.6
has to happen before 2.4."

**Proof:** `01_Data/CORPUS.md` → "Personal legitimate mail", the "Why" paragraph
has the numbers. `02_Model/results/baseline_results.md` has the held-out metrics.

**Numbers to have cold:** 80% vs 37% on `has_http_only_link`. 818 legitimate
test messages. Caution rate 11.9% → 59.2%, dangerous 0.7% → 8.7%.

---

## Item 5 — The system as it stands

**Say:** "The whole pipeline works and is deployed. The extension reads a
message in Gmail, sends it to my server, the server scores it and sends back the
reasons, and the panel shows a severity level with the ranked explanation.
There's an operator dashboard with scan history and the feedback queue."

**Proof — have these tabs open before class:**
- `https://api.usephishlens.app/health`
- `https://api.usephishlens.app/dashboard` (know your password)
- Gmail with the extension loaded, one seeded phishing message ready to open
- The repo: `https://github.com/connorschell/PhishLens`

**Held-out metrics, if asked:** precision 0.8819, recall 0.9561, false-positive
rate on ordinary mail 0.1186, PR AUC 0.9832 — on a 2,546-message held-out split
with 0% measured leakage. **Never say "accuracy."** The test set is 53.7%
phishing and an inbox is not.

---

## Questions he might ask, and answers

**"So is your model broken?"**
"No — the model does what it was trained to do. What's broken is the
measurement. My test set has the same age gap as the training set, so the
reported numbers don't tell me how it behaves on modern mail. That's what the
rebuild fixes."

**"Why didn't you catch this earlier?"**
"I partly did — I ran an ablation in week 4 that removed the six suspect
features, and it cost a lot of recall. What I couldn't do was measure whether
removing them was right, because both the training and test data come from the
same two corpora. Week 8 testing gave me a concrete false positive on a real
message, which is what made it obvious."

**"Will you be ready for the demo on the 30th?"**
"The system demos today — it's deployed and working. What I'm pushing on this
week is the false-positive rate, so the demo shows legitimate mail coming back
clean rather than over-flagged."

**"Why are your hours estimated?"**
"I didn't log them as I worked this week. They're my honest reconstruction and
I've labelled them as estimates rather than presenting them as tracked."
Don't over-apologize. Say it once and move on.

**"Why only 7 hours?"**
"Two of the four tasks were blocked on things outside the code — the Gmail
export, and data that lives on my old laptop. I put the time into finishing 5.3
properly and writing the test plan rather than starting work I'd have to redo."

---

## Risks to raise yourself, before he finds them

Raising these makes you look in control. Hiding them doesn't work.

1. **1.6 → 2.4 is one chain with one week left.** The Takeout export is on
   Google's clock, not mine.
2. **The training data and trained models exist only on my old laptop and the
   server.** Three remaining tasks read them, and retraining on a different
   sample would make my IM1 numbers incomparable with the final ones. Copying
   them is on my list this week.
3. **The backups are on the same server they protect.** Documented, not hidden.

---

## Numbers cheat sheet

| | |
|---|---|
| Hours this week | 7.0 (estimated) |
| Running total | 102.75 of 150 |
| Tasks done | 32 of 47 |
| Tests in the plan | 31, six groups |
| Scans in the database | 143 |
| Precision / recall | 0.8819 / 0.9561 |
| False-positive rate, ordinary mail | 0.1186 |
| The counterfactual | caution 11.9% → 59.2% |
| Change log entries this week | #43, #44 |
