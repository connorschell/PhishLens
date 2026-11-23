# Training Corpus

**WBS 1.1.** Sources, licences, counts, and the decisions behind them.
Connor Schell · CYBR 498W · PhishLens · 2026-09-30

Reproduce with:

```bash
python 01_Data/src/acquire_corpus.py     # writes 01_Data/raw/*.tar.gz + manifest.json
python 01_Data/src/normalize.py          # writes 01_Data/processed/normalized/*.jsonl
```

On a machine with a short job limit, run the two corpora separately:

```bash
python 01_Data/src/normalize.py --only phishing_pot
python 01_Data/src/normalize.py --only spamassassin --append
```

---

## Sources

| Corpus | Role | Messages | Format | Licence | Commit |
|---|---|---|---|---|---|
| SpamAssassin public corpus | Legitimate mail and non-phishing spam | 6,046 | Full RFC 822, one JSON per message | Apache-2.0 | `02b1f0de3e` |
| Phishing Pot | Phishing | 8,614 | `.eml` with intact headers | MIT | `49f6377712` |

`01_Data/raw/manifest.json` records the exact commit, file counts, and byte sizes
of whatever was downloaded, so any result in the final report can be traced back
to a specific version of a specific corpus.

### Deviations from the approved proposal

The proposal named the **SpamAssassin public corpus** and the **Nazario phishing
corpus**. Both changed:

1. **SpamAssassin — same corpus, different host.** `spamassassin.apache.org` is
   not reachable from the build network. The corpus was taken from the
   `stdlib-js/datasets-spam-assassin` mirror on GitHub, which carries the same
   six group directories (`easy-ham-1`, `easy-ham-2`, `hard-ham-1`, `spam-1`,
   `spam-2`) at the same message counts, one JSON file per message with the raw
   text intact. The corpus itself is unchanged.

2. **Nazario — replaced by Phishing Pot.** `monkey.org` is unreachable, and the
   Nazario collection's newest messages are from 2017. Phishing Pot is a
   honeypot collection of real phishing mail from 2022 onward, in `.eml` with
   headers preserved, MIT licensed. Substituting it directly addresses the
   "stale, inconsistent corpora" risk named in WA#3: the phishing class now
   reflects current campaign structure — link shorteners, tracking redirectors,
   and brand impersonation of services that existed after 2017.

Both are recorded as Change Log entry #4 and reported in Weekly Update #2.
No schedule impact; WBS 1.1 completed within its 8-hour estimate.

### Ethical and legal note

The two public corpora are redistributable research datasets. Phishing Pot
samples are anonymized at source: recipient addresses are replaced with
`phishing@pot`. The live-Gmail test accounts in WBS 5.4 are throwaway accounts
seeded from these corpora.

**Amended 2026-11-18 (WBS 1.6).** This note previously read "no message in this
project comes from a real personal inbox." That is no longer true: the modern
legitimate half is the author's own received mail. The conditions under which
that is acceptable are set out in "Personal legitimate mail" below, and the
corresponding disclosure is in `00_Admin/data-handling.md`.

Messages are stored and parsed as inert text. Attachments are recorded by name,
type, and size only — payloads are never written to disk or executed.

### Personal legitimate mail (WBS 1.6)

**Why.** WBS 2.4 established that the model was separating the 2002 legitimate
corpus from the 2022+ phishing corpus rather than separating phishing from
legitimate mail. The decisive evidence: `has_http_only_link` appears in 80% of
the 2002 legitimate messages and 37% of the phishing, so the model learned that
a plain `http` link indicates safety — and modern mail, which is `https`
throughout, is scored as unsafe in consequence. Rescoring the 818 legitimate
test messages with that one feature flipped to `https` raises their caution rate
from 11.9% to 59.2% and their dangerous rate from 0.7% to 8.7%.

No threshold change fixes that, and the ablation comparison cannot measure it,
because the test split is drawn from the same two corpora and therefore contains
the same vintage gap. Modern legitimate mail is the only thing that makes the
measurement valid.

**What is exported.** Received mail from the author's own Gmail account,
excluding Spam and Trash, exported via Google Takeout as mbox. Spam and Trash
are excluded because every message here is labelled `ham` by assumption, and a
phishing message that reached the inbox would be mislabelled.

**What leaves the machine: nothing.** The mbox is read from `01_Data/raw/`,
which is gitignored. Normalization and feature extraction run locally, and the
only artifacts that travel are the split files, which carry a record id, a label
and 43 numbers per message — no subject, no body, no addresses. The corpus is
never committed, never submitted, and never shared.

**Third parties.** These messages were written by other people who did not
consent to being in a training corpus. The mitigations are that the data stays
on the author's own machines, is not redistributed, and that no message content
survives feature extraction. This is recorded rather than glossed.

**Limitation to carry into the report.** A student's inbox is not a neutral
sample of legitimate mail. It is university notices, developer tooling, billing
and newsletters, which is a narrower distribution than the general population
receives. It is, however, the distribution the extension actually runs against.

**Reproducibility.** This half of the corpus is not redistributable, so the
evaluation is not independently reproducible. That is why the held-out metrics,
the ablation comparison and the counterfactual above are reported in full: a
reader who cannot rerun the experiment can still see what it measured.

Reproduce locally with:

```bash
# export from Google Takeout: Mail -> selected label, mbox format
mv ~/Downloads/All\ mail\ Including\ Spam\ and\ Trash.mbox \
   01_Data/raw/personal_ham.mbox
python 01_Data/src/normalize.py --only personal_ham --append
python 01_Data/src/build_dataset.py
```

Messages are stored and parsed as inert text. Attachments are recorded by name,
type, and size only — payloads are never written to disk or executed.

## Storage layout

```
01_Data/raw/
    manifest.json            provenance: URLs, commits, counts, sizes
    spamassassin.tar.gz      9 MB compressed (35 MB uncompressed)
    phishing_pot.tar.gz      215 MB compressed (423 MB uncompressed)
01_Data/processed/normalized/
    phish.jsonl              6,820 records
    spam.jsonl               1,789 records
    ham.jsonl                4,091 records
    normalization_report.json
```

Raw corpora are stored as one compressed archive each rather than ~29,000 loose
files, because the project folder is inside OneDrive and syncing that many small
files takes minutes per change. `normalize.py` streams straight out of the
archives. Set `PHISHLENS_RAW_DIR` to move the archives off the synced drive
entirely; nothing else has to change.

Neither raw nor processed data is committed to git — see `.gitignore`. The
manifest plus the two scripts reproduce both exactly.

## Normalization

Every message, whatever its source format, becomes one record in the schema
defined in `01_Data/src/record_schema.py` (schema version 1.0). The same schema
carries the payload the Chrome extension assembles from the Gmail DOM in WBS 4.2,
so a corpus message and a live message reach the model in identical shape.

The schema marks three fields **corpus-only**: `return_path_address`,
`received_count`, and `auth_results_present`. Gmail's rendered DOM does not
expose `Received` chains or `Authentication-Results`, so the model must not be
trained on them. They are kept for error analysis and to quantify what the
DOM-parsing limitation costs — a number worth reporting rather than hiding.

Per message the normalizer extracts: sender display name, address, domain and
registered domain; `Reply-To` and `Return-Path` with a computed
`sender_mismatch`; subject, recipient, date (raw and ISO), `Message-ID`;
body text with HTML stripped; every hyperlink with its host, registered domain,
and anchor text, flagged where the anchor text names a different domain than the
href; and attachment names, types, and sizes.

## De-duplication

Two passes, both before any train/test split, because a duplicate that straddles
the split inflates every metric in the final report.

1. **Exact** — identical raw bytes. Removed 5 messages.
2. **Near** — identical fingerprint over sender registered domain, subject and
   first 800 characters of body with digits and long hex runs masked. This is
   what catches one phishing template blasted 30 times with a rotating tracking
   ID. Removed 1,954 messages.

A message with neither subject nor body text is exempted from the near pass and
keyed on its own id, so unparsable messages do not collapse into one record.

**Removing 1,788 near-duplicate phishing messages — 21% of that class — is the
single most consequential number in this task.** Left in, they would have
appeared on both sides of the split and made the classifier look far better than
it is.

## Final counts

| Label | Read | Kept | Exact dup | Near dup | Mean links/message |
|---|---|---|---|---|---|
| phish | 8,613 | **6,820** | 5 | 1,788 | 3.96 |
| ham | 4,150 | **4,091** | 0 | 59 | 4.57 |
| spam | 1,896 | **1,789** | 0 | 107 | 3.06 |
| **Total** | **14,659** | **12,700** | 5 | 1,954 | |

### Class balance

Phishing is 54% of the corpus, which is far denser than any real inbox. That is
deliberate — the model needs enough phishing to learn from — but it means
**precision and false-positive rate must be read against a realistic prior, not
against this corpus's base rate.** The evaluation harness in WBS 2.1 reports on a
held-out split with the class balance stated alongside every metric, and WBS 2.4
calibrates severity tiers against legitimate bulk mail specifically.

### Why `spam` is a third label, not merged into `ham`

Unsolicited bulk mail is not phishing, but it shares phishing's surface features:
urgency language, brand imagery, tracking redirectors, sender/domain mismatch. It
is the hardest negative class and the main source of false positives this project
has to survive. Keeping it separate means the evaluation can report false
positives on *spam* apart from false positives on *ham*, which is the number that
actually predicts whether the extension is tolerable in daily use.

The `hard-ham-1` group — 250 legitimate messages that look like spam — is
included in `ham` for the same reason.

## Parse health

48 messages of 14,659 (0.3%) needed a charset fallback, caused by malformed
`Content-Type` headers — several put an entire HTML document in the charset
parameter. 141 messages have no body text (attachment-only or empty), and 40 have
an unparsable `Date`. All are recorded in `normalization_report.json` and none
were dropped on that basis.

## Next

WBS 1.3 (email parser) and 1.4 (feature extractor) build on these records;
WBS 1.5 produces the train/test split and the feature dictionary. Both are due
Weekly Update #3, 2026-10-07.
