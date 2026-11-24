# WBS 2.4 — severity tiering and false-positive analysis

Written 2026-11-24, against the rebuilt corpus from WBS 1.6.

## What this task was blocked on

WBS 2.4 was blocked for a week, and not on threshold tuning. The model had
learned to separate the 2002 legitimate corpus from the 2022+ phishing corpus
rather than separating phishing from legitimate mail. `has_http_only_link`
appeared in 80% of the 2002 legitimate messages and 37% of the phishing, so a
plain `http` link read as evidence of safety, and modern `https` mail was
scored unsafe in consequence.

The decisive measurement was a counterfactual: take the legitimate test
messages, flip that one feature to `https`, and rescore. Before the rebuild,
on 818 legitimate test messages, that raised the caution rate from 11.9% to
59.2% and the dangerous rate from 0.7% to 8.7%. No threshold change can fix
that, and the ablation comparison could not measure it, because the test split
was drawn from the same two corpora and carried the same vintage gap.

## The corpus after the rebuild

Personal legitimate mail was added from the author's own Gmail export (Mail
only, Spam and Trash deselected), normalized locally and deduplicated against
the existing corpus.

| | before | after |
|---|---|---|
| ham | 4,091 | 11,797 |
| phish | 6,818 | 6,818 |
| spam | 1,789 | 1,789 |
| total | 12,698 | 20,404 |

7,706 personal messages were kept out of 8,550 read; 903 near-duplicates were
removed. Train 16,317 / test 4,087, 43 features. The campaign-aware split
reported zero shared record ids, zero shared fingerprints and zero shared
campaigns across train and test.

## The counterfactual, repeated

Same measurement, same feature, on the rebuilt corpus — 2,352 legitimate test
messages:

| | before rebuild (818 legit) | after rebuild (2,352 legit) |
|---|---|---|
| caution rate, as-is | 11.9% | 12.2% |
| caution rate, flipped to https | 59.2% | 17.2% |
| **change** | **+47.3 points** | **+5.0 points** |
| dangerous rate, as-is | 0.7% | 0.9% |
| dangerous rate, flipped to https | 8.7% | 1.2% |
| **change** | **+8.0 points** | **+0.2 points** |

The sensitivity to link scheme has collapsed. The reason is visible in the
corpus itself: `has_http_only_link` now appears in 39.8% of legitimate test
messages and 41.1% of phishing — effectively the same rate, so the feature
carries almost no class information. Its fitted coefficient fell from −2.1481
to −0.4481, an 79% reduction in weight.

This is the result the task was waiting for. The model is now separating
phishing from legitimate mail rather than new mail from old mail.

## Severity tiers

Thresholds are set from a false-positive budget on legitimate mail, measured on
out-of-fold predictions over the training set, never on the test set.

| tier | ham FP budget | threshold | observed ham rate on test |
|---|---|---|---|
| caution | 10.0% | 0.5785 | 12.2% |
| suspicious | 2.0% | 0.8286 | 3.8% |
| dangerous | 0.5% | 0.9385 | 0.9% |

Every tier overshoots its budget on held-out data by roughly a factor of two.
That gap is real and is reported rather than tuned away: tightening the
thresholds against the test set would make the numbers look better and mean
nothing. The honest statement is that the budgets are met in-sample and missed
out-of-sample by about 2x, which is a generalization gap, not a calibration
error.

## Held-out performance

Full model, 43 features, at the caution threshold:

| metric | value |
|---|---|
| precision | 75.5% |
| recall | 83.9% |
| false-positive rate on legitimate mail | 12.2% |
| false-positive rate, all non-phishing | 13.8% |

Accuracy is deliberately not reported. The class balance in the test split is
33.7% phishing, and in a real inbox it would be a fraction of a percent, so an
accuracy figure would be dominated by the majority class and would say nothing
about whether the tool works.

Tier distribution:

| | clear | caution | suspicious | dangerous |
|---|---|---|---|---|
| legitimate | 87.8% | 8.5% | 2.8% | 0.9% |
| phishing | 16.1% | 21.2% | 19.9% | 42.8% |

16.1% of phishing is scored clear. That is the miss rate, and it is the number
to state out loud rather than lead with precision.

Spam is flagged at 24.2%. Spam is not phishing and is not budgeted alongside
legitimate mail: calling unsolicited bulk mail suspicious is a much smaller
wrong than calling a colleague's mail suspicious.

## Ablation

The ablated variant removes the six features flagged by the WBS 1.5
single-feature AUC report: `has_http_only_link`, `link_density_per_100_words`,
`max_url_length`, `subject_has_reply_prefix`, `subject_length`,
`subject_nonascii`.

| | full (43) | ablated (37) |
|---|---|---|
| precision | 75.5% | 73.1% |
| recall | 83.9% | 69.0% |
| ham FPR | 12.2% | 10.5% |

Before the rebuild this comparison was uninformative, because both variants were
trained and tested on the same vintage gap. It now says something: removing
those six features costs 14.9 points of recall for 1.7 points of false-positive
rate. They carry real signal rather than corpus artifact. The full variant
remains the shipped model.

## What still false-positives, and why

Of 2,352 legitimate test messages, 288 were flagged — 200 caution, 66
suspicious, 22 dangerous.

Comparing the flagged legitimate messages against the cleared ones, the
dominant driver is not subtle:

| feature | mean, flagged | mean, cleared |
|---|---|---|
| `link_domain_matches_sender` | 0.076 | 0.653 |
| `no_link_matches_sender_domain` | 0.722 | 0.306 |
| `link_count` (log) | 1.582 | 2.607 |
| `link_density_per_100_words` | 3.265 | 10.053 |

Legitimate mail gets flagged when its links do not point back at the sending
domain. That is the signature of third-party-sent mail: a university notice
delivered through a mailing vendor, a receipt from a payment processor, a
newsletter sent through a campaign platform, a link wrapped in a click-tracking
redirector. The sending domain and the link domain genuinely differ, which is
also exactly what a lookalike phishing message does.

This is a known limitation rather than a defect to tune out. The feature is
doing what it was designed to do; the world contains legitimate mail that looks
structurally like phishing. Reducing it would need sender authentication
signals — SPF, DKIM, DMARC — which the Gmail rendered DOM does not expose and
which this project therefore cannot use.

A secondary cluster: `sender_display_nonascii` is present in 3.8% of flagged
legitimate messages against 0.1% of cleared ones. That is a small number of
messages with non-Latin characters in the display name, which the model treats
as a homograph signal. It is a real signal with a real cost to senders whose
names are not Latin-script, and it is recorded here rather than left implicit.

## Reproducibility note

These figures were produced by rerunning the `train_baseline.py` procedure
against the rebuilt splits. The environment that produced them used
scikit-learn 1.9.1, where the project pins 1.6.0. Logistic regression with the
lbfgs solver is stable across those versions and the coefficients should match
to several decimal places, but the canonical bundle for deployment should be
regenerated locally against the pinned environment before it is pushed to the
production host.

The personal half of the corpus cannot be redistributed, so this evaluation is
not independently reproducible. That is why the counterfactual, the ablation
comparison and the tier budgets are all reported in full: a reader who cannot
rerun the experiment can still see exactly what was measured.

## The headline: the numbers got worse, and that is the result

| at the caution threshold | before rebuild | after rebuild |
|---|---|---|
| precision | 88.2% | 75.5% |
| recall | 95.6% | 83.9% |
| ham FPR | 11.9% | 12.2% |
| dangerous-tier ham FPR | 0.6% | 0.9% |

Read naively this is a regression. It is not. The earlier figures were
measuring a task the tool will never face: telling 2002 mail apart from 2022
mail. Roughly twelve points of precision and twelve points of recall were being
earned by a shortcut that disappears the moment the tool meets a real inbox,
where every message is modern.

The counterfactual is the proof. A model that loses 47 points of caution rate
when you change one link from `http` to `https` is not a phishing detector. A
model that loses 5 points is. The second model scores lower on paper and is the
one that works.

Two things are genuinely harder about the new corpus, and both are real rather
than artifacts. The legitimate half is now dominated by a modern student inbox —
university notices, developer tooling, billing, newsletters — much of which is
sent by third parties on the sender's behalf and therefore looks structurally
like a lookalike attack. And the class balance moved from 53.7% phishing to
33.4%, so the same false-positive count costs more precision.

The figure to present is not the old 88.2%. It is the new 75.5%, with the
counterfactual beside it explaining why the old one was not real.
