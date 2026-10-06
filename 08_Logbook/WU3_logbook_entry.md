# Logbook — Week 3 (WU3)

**Connor Schell · CYBR 498W · PhishLens**
Week ending 2026-10-07 · Weekly Update #3 · **11.0 hours this week**

---

## 2026-10-06 — Parser, feature extractor, dataset split, and review (11.0 hrs)

**1.3 · 2.0 hrs.** Factored the parser out of `normalize.py` into
`01_Data/src/parse_email.py` as a module in its own right, with two entry
points: `parse_raw_message` for corpus `.eml` files and `parse_gmail_payload`
for the payload the extension will scrape from the Gmail page. Both produce the
same record, which is the point — if the two drifted apart, the model would see
one shape in training and a different one in production. `normalize.py` now
imports the parser instead of carrying its own copy, so there is one
implementation and no way for them to diverge.

Wrote 24 unit tests, built from the failure modes the corpus actually contains
rather than invented ones: the 141 messages with no body, the 40 with an
unparsable date, the 48 with a malformed charset parameter. The tests
immediately earned their keep by catching a bug. An anchor whose visible text is
a legitimate-looking URL — `<a href="evil.ru">https://www.paypal.com/account</a>`,
the oldest trick in phishing — was being counted as two links, the real one plus
the display text picked up as a bare URL. That credited the message with a link
to the very brand it was impersonating. Fixed by suppressing anchor display text
before the bare-URL scan.

Came in at 2 hours against a 6-hour estimate, because most of the logic was
already written during WBS 1.1 and this was a restructuring rather than a build.

**1.4 · 3.5 hrs.** Built `01_Data/src/features.py`: 43 named features across
sender, links, structure and language. Set three rules before writing any of
them, and wrote tests that enforce each:

1. Every feature maps to one plain sentence a person would accept as a reason.
   No bag-of-words, no embeddings — a contribution from one of those cannot be
   explained, and explanation is the whole point of this project.
2. No feature may use a field the Gmail page cannot supply. The extension never
   sees the Received chain, Return-Path, or Authentication-Results.
3. No feature may encode which corpus a message came from. The phishing corpus
   anonymises every recipient to `phishing@pot` and is twenty years newer than
   the rest, so recipient, date and Message-ID would separate the classes
   perfectly while learning nothing.

**1.5 · 2.0 hrs.** Built `01_Data/src/build_dataset.py`. Binary target —
phishing against everything else — with the three-way label carried alongside
but never fed to the model, so the evaluation can report false positives on spam
separately from false positives on ordinary mail. That separation is the number
that actually predicts whether the extension is bearable to use daily. Added
leakage checks that refuse to write a split rather than warn about one, and
generated `01_Data/feature_dictionary.md` from the dataset report so the prose
and the numbers cannot drift apart. That dictionary is Deliverable #8.

**1.4 · 3.0 hrs (review and rework).** Ran an independent adversarial review
over everything written this week, specifically looking for defects rather than
confirmation. It found four that mattered, and I fixed all four.

*The three strongest features in the set were measuring the calendar.*
`has_html_part` had a single-feature AUC of 0.88 — nearly separating the classes
on its own. It was not detecting phishing. My phishing corpus is 2022 onward and
my ham and spam are from 2002, so "this message is formatted as HTML" is mostly
a statement about what year it was sent. Worse, at inference the extension
always supplies both HTML and text, so the feature would be pinned to the
phishing value on every real message the tool ever sees. A model leaning on it
would have flagged an entire inbox. Removed it along with `has_text_part`,
`html_without_text_alternative`, and `has_list_unsubscribe` — the last because
the Gmail page does not expose the header at all, so it would have been
silently constant in production.

*One feature was built on a header Gmail never shows.* `sender_mismatch` was
computed from Return-Path as well as Reply-To, which breaks rule 2 above. The
test meant to catch that only searched the text of one function, and the
offending read was one call away in the parser, so it passed while the rule was
broken. In the 2002 ham corpus Return-Path is the mailing-list bounce address,
which made the feature fire on 62% of legitimate mail against 19% of phishing —
not just useless but backwards. Rebuilt on Reply-To alone, and replaced the test
with one that parses real messages differing only in forbidden fields and
asserts the feature vectors are identical.

*A quarter of the test set was the same scam campaigns as the training set.*
The de-duplication in WBS 1.1 keys on sender domain plus subject plus body, and
phishing blasts rotate sender domains, so whole campaigns survived
de-duplication and then landed on both sides of the split. Measured: 29.7% of
test phishing shared a masked subject with a training record. Testing a model on
messages it has effectively already seen produces a flattering number that means
nothing. Replaced the stratified split with union-find grouping over masked
subject or first 200 characters of body, merged transitively so a campaign that
varies one field at a time is still caught as one unit. 7,904 campaigns. Leakage
re-measured at 0%.

*Keyword matching was substring-based and would have produced false
explanations.* "chase" was being found inside "purchase", "ups" inside "Yahoo
Groups", "lock" inside "unblock". These are not cosmetic — they reach the user
as a stated reason, so the extension would have told someone "this message
claims to be from Chase" about an ordinary receipt. Rebuilt on word boundaries,
with inflections collapsed so "expire", "expires" and "expiring" count as one
reason rather than three.

Also fixed in the same pass: Gmail's `saferedirect` link rewriting is now
unwrapped before anything reads a link's host; display mismatch now catches bare
domains in anchor text, which is how phishing actually renders it and was
roughly four times more common than the full-URL form the code was looking for;
attached `.eml` files are recorded as attachments instead of having their body
text merged into the parent message; inline images and tracking pixels are no
longer counted as attachments; IP-literal links no longer get a fabricated
registrable domain; character-set failures are recorded instead of decoding
silently to replacement characters; and the `phishing@pot` anonymisation token
is stripped from subject and body, where it appeared in 22% of phishing messages
and zero legitimate ones.

Added 13 regression tests, one per defect. Suite is now 59 tests, all passing.

**A-04 · 0.5 hr.** Wrote Weekly Update 3 as `07_WeeklyUpdates/WU3.docx`, in
plain language with the week 2 recap at the top and a table mapping each piece
of the week's work to its file path.

---

## What I would tell someone about this week

The code was finished in about seven hours. The review and rework took three
more, and those three were the most valuable of the week. Without them I would
have trained a model that scored extremely well and was reading the gap between
2002 and 2022 rather than anything about phishing, and I would not have found
out until the final demo, if at all.

The honest consequence: my numbers next week will be lower than they would have
been on the old split and the old feature set. That is the correct direction.

## Open at the end of the week

- **A-01 (TOC page numbers) — still blocked**, second week running.
  `Schell_Connor_Project_Proposal.docx` is still not in the capstone folder.
- **A-04** — WU3 document written; Scholar submission and the in-class standup
  are still to do.
- **Gmail DOM verification — unscheduled, about an hour.** I have written the
  code to unwrap Gmail's link rewriting but have not confirmed it against a real
  message. If Gmail rewrites every href and the unwrapping fails, eight
  link-based features break in the live product while continuing to look fine in
  training. This should happen before I trust anything WBS 2.1 produces.

## Next week (WU4 period, baseline model due the week of 10/12)

WBS 2.1, the baseline classifier and evaluation harness (10 hrs). Precision,
recall and false-positive rate, never accuracy, with the class balance stated
beside every number. Metrics reported twice — full feature set, and with the six
remaining high-AUC features ablated. If the numbers hold up under ablation those
features were honest; if they collapse, the model was reading the calendar. That
comparison goes in the final report either way.
