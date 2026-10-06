# Feature Data Dictionary

**Deliverable #8 · WBS 1.4 and 1.5.** Every input the PhishLens model receives.
Connor Schell · CYBR 498W · generated 2026-10-06T20:17:49+00:00 from `01_Data/processed/splits/dataset_report.json`

**43 features** over **12,698 messages** (10,152 train / 2,546 test).

Regenerate with `python 01_Data/src/build_dataset.py && python 01_Data/src/make_feature_dictionary.py`. The prose is written by hand; every number is read from the dataset report, so the two cannot drift apart.

---

## How to read this

- **Phish mean / Legit mean** — average value of the feature in each class. Binary features read as a proportion: 0.95 means 95% of messages have it.
- **AUC** — how well the feature alone separates the classes. 0.5 is useless; far from 0.5 either way means one feature nearly does the job on its own, which on this corpus is a reason for suspicion before it is a reason for confidence.
- **Same-era gap** — the control. Average difference between *spam and ham*, which both come from the SpamAssassin corpus and the same year. See the warning below.
- **Explanation shown to the user** — the sentence WBS 2.3 will display when this feature contributes materially to a verdict. Every feature has one. That is the design constraint: a feature nobody can explain does not belong in this model.

## The warning that matters

The phishing messages are from 2022 onward. The legitimate and spam messages are from 2002. **Any feature that tracks the era of an email rather than its intent will appear to separate the classes almost perfectly while telling us nothing about phishing.**

The spam-vs-ham column is the control for this. Spam and ham share a source and a year, so a feature that also separates them is doing real work. A feature that separates only across the corpora is suspect.

**6 features have a single-feature AUC far enough from 0.5 to warrant review:** `has_http_only_link`, `link_density_per_100_words`, `max_url_length`, `subject_has_reply_prefix`, `subject_length`, `subject_nonascii`.

These are kept rather than deleted, because some may be genuine — phishing really does use longer URLs and more digits in domains. The obligation is on the evaluation: **WBS 2.1 must report precision, recall and false-positive rate twice — once with the full feature set and once with these ablated.** If the numbers barely move, the features were honest. If they collapse, the model was reading the calendar. That comparison belongs in the final report either way.

The durable fix is a modern legitimate-mail corpus, which would remove the era gap at source. That is recorded as a risk rather than scheduled work, because it would mean re-running WBS 1.1 and there is no obvious freely redistributable source of recent ordinary inbox mail.

## Rules every feature obeys

1. **Individually explainable.** Each feature maps to one sentence a person would accept as a reason. There are no bag-of-words or embedding dimensions, because a contribution from one cannot be explained, and explanation is the point of this project.
2. **Available at inference time.** The extension reads Gmail's rendered page. It never sees the Received chain, Return-Path, or Authentication-Results, so no feature uses them. A test asserts this.
3. **No corpus identity.** Recipient address, date, and Message-ID are excluded. The phishing corpus anonymises every recipient to `phishing@pot` and is 20 years newer than the rest, so any of those would separate the classes perfectly and learn nothing. A test asserts this too.
4. **Properties, not identities.** The sending domain is used to ask whether it matches a link domain, never as a value itself. One-hot encoding domains would memorise the corpus.

## Known limitation: language

The urgency, threat, credential, and financial word lists are English only. The phishing corpus contains German, Portuguese, and other non-English samples, which will score low on all four regardless of content. Expect lower recall on non-English phishing, and expect `subject_nonascii` to carry weight it has not earned. Language detection, or per-language word lists, is the obvious extension and is out of scope this semester.

---

## The features

### Sender

| Feature | Measures | Phish | Legit | AUC | Same-era gap | Flag |
|---|---|---|---|---|---|---|
| `sender_domain_length` | Character length of the sending domain. | 11.9567 | 10.6622 | 0.5945 | 0.7008 |  |
| `sender_domain_digit_count` | Digits in the sending domain. | 0.4044 | 0.0446 | 0.5326 | 0.079 |  |
| `sender_domain_subdomain_depth` | Subdomain levels below the registrable domain. | 0.3938 | 0.2376 | 0.5303 | 0.2065 |  |
| `sender_display_nonascii` | Display name contains non-ASCII characters. | 0.141 | 0.0073 | 0.5668 | 0.0017 |  |
| `sender_domain_hyphen_count` | Hyphens in the sending domain. | 0.0811 | 0.0262 | 0.5173 | 0.0033 |  |
| `brand_claimed_in_display_or_subject` | A known brand is named in the display name or subject. | 0.0544 | 0.0099 | 0.5223 | 0.011 |  |
| `brand_claimed_but_sender_unrelated` | A brand is claimed but the sending domain is unrelated to it. | 0.0497 | 0.0095 | 0.5201 | 0.0113 |  |
| `sender_reply_to_mismatch` | Reply-To is a different registrable domain than From. | 0.1317 | 0.1679 | 0.4819 | 0.0565 |  |
| `sender_is_freemail` | From domain is a free consumer mail provider. | 0.071 | 0.1066 | 0.4822 | 0.2444 |  |
| `sender_domain_suspicious_tld` | Sending domain uses a cheap or widely abused suffix. | 0.0114 | 0.0 | 0.5057 | 0.0 |  |
| `sender_display_contains_email` | Display name itself contains an @ address. | 0.011 | 0.0075 | 0.5018 | 0.0133 | flat |

**Explanations shown to the user:**

- `sender_domain_length` — "The sending domain is unusually long."
- `sender_domain_digit_count` — "The sending domain contains digits, which is uncommon for established brands."
- `sender_domain_subdomain_depth` — "The sending address uses several subdomain levels."
- `sender_display_nonascii` — "The sender's name uses characters that can be used to imitate ordinary letters."
- `sender_domain_hyphen_count` — "The sending domain contains hyphens, often used to mimic a real brand name."
- `brand_claimed_in_display_or_subject` — "This message names a well-known company."
- `brand_claimed_but_sender_unrelated` — "This message claims to be from a well-known company, but it was not sent from that company's domain."
- `sender_reply_to_mismatch` — "Replies to this message would go to a different company than the one it appears to be from."
- `sender_is_freemail` — "This was sent from a free personal email account rather than a company domain."
- `sender_domain_suspicious_tld` — "The sender's domain uses an address suffix frequently used for throwaway registrations."
- `sender_display_contains_email` — "The sender's display name is written to look like an email address."

### Links

| Feature | Measures | Phish | Legit | AUC | Same-era gap | Flag |
|---|---|---|---|---|---|---|
| `max_url_length` | Longest URL (log scale). | 4.0454 | 3.3364 | 0.7278 | 0.2283 | artifact? |
| `has_http_only_link` | At least one link uses unencrypted http. | 0.3671 | 0.8129 | 0.2771 | 0.007 | artifact? |
| `link_count` | Number of links (log scale). | 1.2771 | 1.0187 | 0.6341 | 0.0581 |  |
| `max_subdomain_depth` | Deepest subdomain nesting across links. | 1.6103 | 1.7673 | 0.4218 | 0.001 |  |
| `has_url_shortener` | A link uses a known URL shortener. | 0.1233 | 0.0009 | 0.5612 | 0.0012 |  |
| `distinct_link_domain_count` | Number of distinct destination domains (log scale). | 0.7302 | 0.8277 | 0.4274 | 0.111 |  |
| `link_domain_matches_sender` | At least one link goes to the sender's own domain. | 0.0917 | 0.1639 | 0.4639 | 0.0412 |  |
| `has_ip_literal_link` | A link points at a bare IP address. | 0.0141 | 0.048 | 0.4831 | 0.1528 |  |
| `has_link_display_mismatch` | At least one display/destination mismatch. | 0.0452 | 0.016 | 0.5146 | 0.0069 |  |
| `link_display_mismatch_count` | Links whose visible text names a different domain than the destination (log scale). | 0.0405 | 0.0136 | 0.5146 | 0.0045 |  |
| `no_link_matches_sender_domain` | Message has links, none to the sender's domain. | 0.6603 | 0.6872 | 0.4865 | 0.0108 |  |
| `has_suspicious_tld_link` | A link domain uses a cheap or widely abused suffix. | 0.018 | 0.0005 | 0.5088 | 0.0007 |  |
| `has_userinfo_in_url` | A URL contains an @ before the host. | 0.0176 | 0.0056 | 0.506 | 0.0176 |  |
| `brand_name_in_link_subdomain` | A brand name appears in the subdomain rather than the registrable domain. | 0.0098 | 0.0051 | 0.5024 | 0.0073 | flat |
| `has_punycode_link` | A link host uses punycode (xn--). | 0.0001 | 0.0 | 0.5001 | 0.0 | flat |

**Explanations shown to the user:**

- `max_url_length` — "This message contains an unusually long web address."
- `has_http_only_link` — "A link uses an unencrypted connection."
- `link_count` — "This message contains an unusual number of links."
- `max_subdomain_depth` — "A link uses deeply nested subdomains, which can push a familiar name to the left of the real domain."
- `has_url_shortener` — "A link uses a shortening service, which hides the real destination."
- `distinct_link_domain_count` — "The links in this message point to several different websites."
- `link_domain_matches_sender` — "At least one link goes to the same company that sent the message."
- `has_ip_literal_link` — "A link points directly at a numeric internet address instead of a domain name."
- `has_link_display_mismatch` — "A link displays one website address but actually goes to a different one."
- `link_display_mismatch_count` — "Several links display one website address while actually going to another."
- `no_link_matches_sender_domain` — "None of the links go to the company this message appears to be from."
- `has_suspicious_tld_link` — "A link points to a domain with an address suffix frequently used for throwaway registrations."
- `has_userinfo_in_url` — "A link is formatted so the part before the @ looks like a familiar website, while the real destination comes after it."
- `brand_name_in_link_subdomain` — "A link puts a well-known company's name in the subdomain, while the actual site belongs to someone else."
- `has_punycode_link` — "A link uses an internationalised domain that can be made to look like a familiar name."

### Structure

| Feature | Measures | Phish | Legit | AUC | Same-era gap | Flag |
|---|---|---|---|---|---|---|
| `link_density_per_100_words` | Links per 100 words of body text. | 2.5387 | 1.5045 | 0.6679 | 0.4432 | artifact? |
| `body_word_count` | Words in the body (log scale). | 4.3397 | 4.972 | 0.3598 | 0.1033 |  |
| `body_is_very_short` | Fewer than 20 words of body text. | 0.1698 | 0.043 | 0.5634 | 0.0024 |  |
| `attachment_count` | Number of attachments (log scale). | 0.0386 | 0.0044 | 0.5217 | 0.0021 |  |
| `has_risky_attachment` | An attachment uses an executable or archive extension. | 0.0003 | 0.0 | 0.5001 | 0.0 | flat |

**Explanations shown to the user:**

- `link_density_per_100_words` — "This message is mostly links with very little text around them."
- `body_word_count` — "The message body is unusually short or long."
- `body_is_very_short` — "The message says very little, relying on a link or an image instead."
- `attachment_count` — "This message carries attachments."
- `has_risky_attachment` — "This message carries an attachment of a type commonly used to deliver malware."

### Language

| Feature | Measures | Phish | Legit | AUC | Same-era gap | Flag |
|---|---|---|---|---|---|---|
| `subject_length` | Characters in the subject line. | 56.2033 | 38.1716 | 0.6804 | 2.869 | artifact? |
| `subject_nonascii` | Subject contains non-ASCII characters. | 0.4127 | 0.0119 | 0.7004 | 0.0311 | artifact? |
| `subject_has_reply_prefix` | Subject starts with Re:, Fwd: or Fw:. | 0.0459 | 0.3816 | 0.3321 | 0.4626 | artifact? |
| `subject_exclamation_count` | Exclamation marks in the subject. | 0.3227 | 0.1456 | 0.5886 | 0.3652 |  |
| `subject_allcaps_word_count` | Words in all capitals in the subject. | 0.3348 | 0.4818 | 0.4572 | 0.3993 |  |
| `financial_term_count` | Distinct payment or money phrases found. | 0.2184 | 0.116 | 0.5424 | 0.2487 |  |
| `urgency_term_count` | Distinct urgency phrases found. | 0.1819 | 0.0932 | 0.5357 | 0.189 |  |
| `credential_term_count` | Distinct credential or sign-in phrases found. | 0.0887 | 0.0347 | 0.5144 | 0.0298 |  |
| `threat_term_count` | Distinct threat or account-status phrases found. | 0.0673 | 0.0378 | 0.5122 | 0.0053 |  |
| `has_generic_greeting` | Opens with a generic greeting rather than a name. | 0.0301 | 0.0128 | 0.5087 | 0.0411 |  |
| `subject_is_empty` | Subject line is empty. | 0.006 | 0.0026 | 0.5017 | 0.006 | flat |
| `body_allcaps_ratio` | Proportion of all-capital words in the body. | 0.0384 | 0.0356 | 0.4519 | 0.0405 | flat |

**Explanations shown to the user:**

- `subject_length` — "The subject line is unusually long."
- `subject_nonascii` — "The subject line uses non-standard characters."
- `subject_has_reply_prefix` — "The subject is formatted as a reply or forward."
- `subject_exclamation_count` — "The subject line uses exclamation marks for emphasis."
- `subject_allcaps_word_count` — "The subject line shouts in capital letters."
- `financial_term_count` — "The message refers to payments, invoices, or money."
- `urgency_term_count` — "The message pressures you to act immediately."
- `credential_term_count` — "The message asks you to sign in, verify your identity, or confirm account details."
- `threat_term_count` — "The message warns that your account is suspended, locked, or at risk."
- `has_generic_greeting` — "The message greets you generically instead of by name."
- `subject_is_empty` — "This message has no subject line."
- `body_allcaps_ratio` — "Much of the message is written in capital letters."

---

## Features with no measured separation

These show almost no difference between classes in this corpus. They are kept because most are rare-but-decisive signals: a punycode link or an executable attachment is strong evidence when it appears, and prevalence this low simply means it rarely appears. `body_allcaps_ratio` has no such defence and is the first candidate for removal if the model needs trimming.

| Feature | % of phishing with it | % of legitimate with it |
|---|---|---|
| `body_allcaps_ratio` | 60.72% | 76.19% |
| `brand_name_in_link_subdomain` | 0.98% | 0.51% |
| `has_punycode_link` | 0.01% | 0.0% |
| `has_risky_attachment` | 0.03% | 0.0% |
| `sender_display_contains_email` | 1.1% | 0.75% |
| `subject_is_empty` | 0.6% | 0.26% |

## Dataset and split

- Split: **80/20**, stratified on the three-way label, seed `20260930`.
- Phishing share: **53.7%** of train, **53.7%** of test.
- Leakage: **0** shared record ids, **0** shared near-duplicate fingerprints. The build refuses to write a split if either is non-zero.

**The target is binary** — 1 for phishing, 0 for legitimate or spam. The three-way label rides along as `label_3way` and is never fed to the model; it exists so WBS 2.1 can report false positives on spam separately from false positives on ordinary mail. That split is the number that predicts whether the extension is tolerable in daily use.

**Phishing is 54% of this corpus and nothing like that in a real inbox.** Precision and false-positive rate must be read against a realistic prior, with the class balance stated next to every metric.

## Class balance

| Split | Phishing | Legitimate | Spam | Total |
|---|---|---|---|---|
| overall | 6,818 | 4,091 | 1,789 | 12,698 |
| train | 5,451 | 3,273 | 1,428 | 10,152 |
| test | 1,367 | 818 | 361 | 2,546 |

