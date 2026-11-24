# WU9 proof sheet

Where to find evidence for each thing you did this week. Monday 23 November.

---

## WBS 5.3 — database backups

*Proves the backups exist, run on a schedule, and have actually been restored.
The live script run is the strongest single thing you can show — five seconds.*

- `05_Deployment/backup/` — `backup.sh`, `restore_test.sh`, 4 systemd unit files, `README.md`
- Run live: `./05_Deployment/backup/restore_test.sh` → ends `RESTORE TEST PASSED`
- `systemctl list-timers 'phishlens-*'` → both timers scheduled
- `ls -lh /var/backups/phishlens/` → dump files on disk
- `journalctl -u phishlens-backup.service -n 10 --no-pager` → `table of contents verified` / `backup complete`

---

## WBS 5.4 — end-to-end test plan

*Proves the plan exists and is honest. If he asks whether it's realistic, show
Group D — the cases you already know fail.*

- `05_Deployment/test_plan_and_results.md` — 31 cases, six groups, Group D = known failures

---

## WBS 1.6 — training data groundwork

*Proves the code and the ethics write-up are done, and that the export gets
checked before it's trusted. The CORPUS.md section is the writing-intensive part.*

- `01_Data/CORPUS.md` → section "Personal legitimate mail (WBS 1.6)"
- `01_Data/src/normalize.py` → `read_personal_ham()`
- `01_Data/src/verify_ham_export.py`

---

## The finding — why 2.4 is blocked

*Proves you measured the problem instead of guessing. These are the numbers to
have in front of you: 80% vs 37%, and 11.9% → 59.2%.*

- `01_Data/CORPUS.md` → "Why" paragraph
- `02_Model/results/baseline_results.md` → held-out metrics
- Tracker → Change Log #44

---

## A-12 — the weekly update itself

*Proves the tracker is current and the hours are recorded, in case he asks to
see the plan of record rather than the document.*

- `07_WeeklyUpdates/WU9.docx`
- `08_Logbook/WU9_logbook_entry.md`
- `07_WeeklyUpdates/WU9_standup_notes.md`
- Tracker → Tasks tab, Time Log (4 rows dated 11/22), Change Log #43 and #44, Weekly Updates tab WU9

---

## The system as it stands

*Have these open before class. This is what you fall back on if the
conversation turns to "show me it works."*

- `https://api.usephishlens.app/health`
- `https://api.usephishlens.app/dashboard`
- `https://github.com/connorschell/PhishLens`
- Gmail tab with the extension loaded and a seeded message ready to open
