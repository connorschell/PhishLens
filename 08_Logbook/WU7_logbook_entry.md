# Week 7 logbook entry — week ending 11 November 2026

PhishLens · CYBR 498W · Connor Schell

## Hours

11 hours against 16.5 estimated. The extension work came in close to estimate;
the deck took less than budgeted because the mockups drawn in week 6 already
answered what the interface should look like. Running total 84 hours. The half hour of wiring that pointed the extension at a local API is logged against week 6, where it was worked.

| Task | Hours | What was done |
|---|---|---|
| 4.3 | 4.0 | Panel UI — verdict, tiers, and the four non-verdict states |
| 4.2 | 3.0 | Gmail DOM parsing and payload assembly |
| A-09 | 2.0 | IM2 deck, repository README, demo runbook |
| 4.4 | 1.5 | Feedback control — note field and failure reporting |
| A-10 | 0.5 | Weekly update |

## What was completed

This is the week PhishLens became a working system rather than a set of working
parts. Opening a message in Gmail now produces a scored, explained panel above
the message body, end to end, with no manual steps.

WBS 4.2 reads the message out of the page. This is the most fragile code in the
project and it is isolated deliberately: Gmail's class names are build artifacts
that change without notice, so every selector lives in one file and nothing else
in the extension knows they exist. Where possible it reads attributes rather than
classes — `span[email]` has outlived several redesigns of everything around it.
Quoted history and signatures are stripped before scoring, because a reply that
quotes a phishing message is not itself phishing, and leaving the quote in would
score the thread instead of the message in front of the user. Every field is
truncated below the server's limits so a long thread truncates client side rather
than being rejected.

Testing it caught a real bug. Gmail encodes attachment metadata as
`mimetype:filename:url`, and I was taking the last colon-separated segment, which
returned a fragment of the URL instead of the filename — the URL contains colons
of its own.

WBS 4.3 built the panel. Two rules govern it. It computes nothing: the score,
the tier, the headline and the bar widths all arrive from the server, because a
panel that derived the tier itself could disagree with the model and show the
user a verdict nothing produced. And every string from the server is inserted as
text rather than markup — the server is trusted, but a message body is not, and
nothing originating in an email may become live HTML inside Gmail's page.

The clear tier collapses to a single line. A panel that announces itself in full
on every message is a panel users stop seeing, including on the one that matters.

WBS 4.4 finished the feedback control, a week ahead of its slot. Two choices and
an optional note capped at 500 characters to match the database constraint. The
thank-you is not shown optimistically: the panel waits for the server's answer
and says which happened, because telling someone their report was recorded and
then dropping it breaks the only promise the control makes.

A-09 produced the IM2 deck, nine slides with speaker notes and a timing budget
against the seven-minute cut. Building it surfaced a stale example in the
repository README — the `/scan` sample had been written before 3.4 made the
token mandatory, so anyone following the README would have got a 401. That
matters this week specifically, because the assignment requires submitting a
repository link and a README describing the contents.

## The demo constraint, and how it was removed

IM2 requires demonstrating functional aspects of the project; screenshots and
mockups are explicitly not sufficient. The deployed server is still plain HTTP
on a bare IP, which would have made a live demo against it both insecure and
contrary to the project's own design document.

The resolution is that the extension points at `http://localhost:8000` for the
demo. Chrome treats localhost as a trustworthy origin — it is the one plain-HTTP
address that is not downgraded, because nothing leaves the machine. So the demo
runs with no certificate at all, while the deployed server still requires HTTPS.
The blocked hostname now affects the public deployment and deliverable #14, not
the milestone.

## Still blocked

WBS 5.2, unchanged from last week. No hostname, so no certificate, so no HTTPS
on the deployed server. The free domain depends on the Student Pack application
pending since September; if it does not clear this week the domain gets bought
outright rather than waited on any longer.

## Next

Safe Browsing integration (3.5) and the web dashboard (4.5) in week 8, then
severity calibration against legitimate bulk mail in week 9 — the false-positive
rate is the number that decides whether anyone keeps this installed.
