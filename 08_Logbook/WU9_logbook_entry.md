# Week 9 logbook entry — week ending 23 November 2026

PhishLens · CYBR 498W · Connor Schell

## Hours

6.5 hours this week, estimated after the fact rather than tracked live.
Running total 102.25 of 150 planned.

| Task | Hours | What was done |
|---|---|---|
| 1.6 | 2.0 | Personal-mail reader in `normalize.py`; corpus ethics and limitations written up in `CORPUS.md` |
| 5.3 | 2.0 | Backup script, restore verification, systemd timer units, runbook |
| 5.4 | 1.5 | End-to-end test plan — 31 cases across six groups |
| A-12 | 1.0 | Weekly Update #9 and this entry |

## What was completed

**WBS 5.3, automated backups with a verified restore.** `pg_dump` in custom
format through `docker compose exec`, because Postgres runs in a container with
no published port outside the Docker network — the same decision WBS 5.1 made
when it left 5432 out of the firewall rules. Nightly at 03:12 UTC on a systemd
timer with `Persistent=true`, so a night the droplet spent rebooting produces a
backup on the next boot rather than a silent gap. Seven daily copies and four
weekly.

Three details in the script exist because of specific failure modes rather than
general caution. The dump is written to a `.part` file and renamed only on
success, so a run killed halfway cannot leave a truncated file that looks like a
backup until the day it is needed. A size floor rejects anything under 20 KB,
which is what a dump of the wrong or an empty database looks like — the schema
alone is larger than that. And every finished dump is opened with
`pg_restore --list`, so no file enters the retention set without something that
understands the format having read its table of contents.

The part that makes the deliverable honest is the restore test, not the dump. It
restores into a throwaway database, dropped on exit through a trap so a failed
run does not leave debris, and then checks four things: that all six WBS 3.1
tables came back; that foreign key constraints survived, because a restore
without them answers every `SELECT` correctly today and corrupts data on the
first write; that row counts are not *below* production's; and that the
`scans × indicators` join the dashboard depends on still runs. Tables existing is
not the same as the application working against them. It runs weekly on its own
timer, after the Sunday dump.

`pg_restore --exit-on-error` is deliberate throughout. A restore that logs errors
and continues produces a database that is partly right, which is the worst thing
to discover during an actual recovery.

Three limitations are written into the runbook rather than left implied. The
backups live on the droplet they protect, so they cover a bad migration or a
dropped table during the final-week deployment, not loss of the host. There is
no encryption at rest — the dumps hold no message content by design, but they do
hold per-install tokens, and the control actually in place is file permissions.
And nightly dumps mean up to 24 hours of loss; WAL archiving would narrow that
and is more than a 3-hour task on a $12/month droplet can carry.

**WBS 5.4, the end-to-end test plan.** The system has been tested in pieces all
semester. This is the first plan that treats the whole chain as one thing: a real
message open in a real Gmail tab, parsed from the rendered DOM, scored by the
deployed API over HTTPS, explained in the panel. 31 cases in six groups —
registration and transport, DOM parsing, scoring and explanation fidelity, known
failures, feedback and the operator view, and failure recovery.

Two findings from week 8 shaped it directly. A message the model already rates
`dangerous` hides a rule-layer floor completely, so the Safe Browsing case
specifies a message the model rates `caution` whose only problem is where its
link goes — otherwise the test passes while measuring nothing. And the short
legitimate message with a `cnu.edu` link that scored `dangerous` is written in as
case D1, expected to fail. A whole group is set aside for cases that are known to
fail today, because leaving them out would produce a test plan that passes and a
product that does not.

The scope boundary is stated in the document: this plan answers whether the
pipeline delivers the model's verdict faithfully. It does not measure precision
or recall. A live run over a few dozen seeded messages is not an evaluation and
is not reported as one — that is WBS 5.5, on the held-out split, after 1.6.

**WBS 1.6, groundwork only.** The reader for a personal mbox export is written
and the corpus documentation now carries the section that has to exist before
any of that mail is used: why personal mail is necessary, what is exported, what
leaves the machine (nothing — the splits carry a record id, a label and 43
numbers), the fact that these messages were written by third parties who did not
consent to being in a training corpus, and the limitation that a student's inbox
is not a neutral sample of legitimate mail. The Google Takeout export itself has
not been done, so the corpus has not been rebuilt.

## What is blocked, and why it matters more than it looks

**WBS 2.4 cannot start.** The diagnosis is already in hand and it is worse than a
threshold problem: the model has been separating the 2002 legitimate corpus from
the 2022-onward phishing corpus rather than separating phishing from legitimate
mail. `has_http_only_link` appears in 80% of the 2002 legitimate messages and 37%
of the phishing, so the model learned that a plain `http` link indicates safety —
and modern mail, which is `https` throughout, is scored as unsafe in consequence.
Rescoring the 818 legitimate test messages with that one feature flipped to
`https` raises their caution rate from 11.9% to 59.2% and their dangerous rate
from 0.7% to 8.7%.

No threshold change fixes that, and the existing ablation comparison cannot
measure it, because the test split is drawn from the same two corpora and carries
the same vintage gap. Modern legitimate mail is the only thing that makes the
measurement valid. So 2.4 depends on 1.6, 1.6 depends on the Takeout export, and
the export takes however long Google takes.

**The corpora and trained bundles exist only on the old laptop and the server.**
They are excluded from the repository by design. WBS 1.6, 2.4 and 5.5 all read
them, and retraining against a different sample would make the IM1 numbers
incomparable with the final ones. Copying them somewhere durable is now on the
critical path, not housekeeping.

## Position

Week 9 was planned as 22 hours across four tasks and did not land as planned.
5.3 and 5.4 are written but neither has been executed against the droplet. 1.6 is
groundwork only. 2.4 has not started and cannot until 1.6 does.

What is genuinely done this semester: the full pipeline from corpus to extension
panel, deployed over HTTPS, with Safe Browsing, an operator dashboard, and a
feedback loop. What is not: the calibration that decides whether the false
positive rate is low enough for anyone to keep the extension installed. That is
the remaining risk, and it is concentrated in a single dependency chain with the
final demo one week out.

## Notes

The tracker workbook has reverted three times this semester (10/2, 11/3, 11/9),
losing the most recent session's edits each time while code files survived —
most likely OneDrive conflict resolution against a copy held open in Excel. A
backup is taken before each edit. If it recurs, the workbook moves out of the
synced folder.
