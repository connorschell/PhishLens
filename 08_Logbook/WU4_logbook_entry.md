# Week 4 logbook entry — week ending 21 October 2026

PhishLens · CYBR 498W · Connor Schell

## Hours

12.5 hours across six sessions on 15 October, against 30 hours estimated for the
WBS 2 tasks in the proposal. The gap is carry-forward: the feature extractor and
the dataset builder from week 3 did most of the work that WBS 2.1 was budgeted
for. Running total 37 hours.

| Task | Hours | What was done |
|---|---|---|
| 2.1 | 3.5 | Baseline classifier and evaluation harness, both variants |
| 2.2 | 1.5 | Per-feature contribution extraction |
| 2.3 | 2.0 | Explanation templating and the rule layer |
| A-21 | 2.0 | Intermediate Milestone 1 demo |
| A-05 | 2.5 | Intermediate Milestone 1 deck |
| A-22 | 1.0 | Intermediate Milestone 1 written status report |

## What was completed

WBS 2.1, 2.2 and 2.3 are done, which closes all of work area 2 except the
calibration task scheduled for week 9. Eight of twenty-five WBS subtasks are now
complete and no milestone has been missed.

The classifier is an L2-regularised logistic regression over the 43 features,
trained on 10,152 campaign-split records and evaluated on 2,546 held out. At the
dangerous tier it reaches precision 0.989 and recall 0.794, with a false-positive
rate of 0.6% on ordinary correspondence and 1.9% on bulk mail. Accuracy is not
reported anywhere, because the test split is 53.7% phishing and an inbox is not.

Severity tier thresholds are derived from a false-positive budget on ordinary
mail — 0.5%, 2% and 10% — measured on out-of-fold training predictions so the
test split stays sealed until the final measurement.

The contribution extractor decomposes the score algebraically rather than
approximating it. The reconstruction is asserted over the entire held-out split,
worst error 1.6e-14. The explanation layer sits on top of it as two separate
layers: one sentence template per feature, ranked by each signal's share of the
evidence for this particular message, and a deterministic rule layer that fires
regardless of model weight. No LLM anywhere in the scoring path. The repository
suite is now 67 tests, all passing.

## The failed ablation

Week 3 flagged six features as possible corpus artifacts and committed to testing
the model with and without them. That test ran and the model failed it. At a
matched 1% false-positive budget on ordinary mail, recall falls from 0.847 to
0.306 without those six. They are carrying the model.

Two of the six are demonstrably artifacts, visible in the learned weights
themselves: `has_http_only_link` and `subject_has_reply_prefix` both carry
negative weights, meaning the model treats an unencrypted link and a "Re:" subject
as evidence of legitimacy. That is a description of 2002 mailing-list traffic, not
of phishing. `max_url_length` carries the largest weight in the model at +4.30,
roughly three times anything else, and is the hardest of the six to adjudicate:
long tracking URLs are real in modern phishing, but 2002 mail had shorter URLs for
reasons unrelated to phishing.

Corpus data cannot settle this. WBS 5.4 live-Gmail testing in week 9 does. Until
then the ablated model stands as the conservative floor and both result sets are
carried in the final report.

## Open items

1. **Privacy decision, newly surfaced.** `parse_gmail_payload` takes the subject,
   sender, body text and body HTML, which means message content leaves the browser
   and the server does the parsing. The alternative is extracting features client
   side so only the 43 numbers leave. This is a real design decision and it belongs
   in the WBS 3.1 schema work next week.
2. **A-01**, the proposal table-of-contents correction, still blocked on the
   approved .docx.
3. **A-18**, the Intermediate Milestone 1 design artifacts named in the proposal
   (stakeholders, user stories, domain model, architecture diagram), not started.
4. **Gmail link rewriting** — needs checking before WBS 4.2, since it would change
   several link features between training and production.
5. **GitHub token expires 30 October.** Rotate in the week of 26 October or pushes
   begin failing with a 403.

## Changes recorded this week

Three entries added to the Change Log tab, all reported in Weekly Update 4:
the shipped model fixed as logistic regression with a tree ensemble measured as a
reference ceiling only; severity thresholds derived from a false-positive budget
rather than fixed score bands; and the ablation result itself, which raises the
stakes of week 9 live testing.
