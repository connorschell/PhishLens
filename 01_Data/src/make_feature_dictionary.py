"""Generate 01_Data/feature_dictionary.md (Deliverable #8) from the dataset report.

The prose lives here; every number is read from dataset_report.json, so the
dictionary cannot drift away from the data. Re-run after any change to
features.py or the corpus.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]
REPORT = DATA_DIR / "processed" / "splits" / "dataset_report.json"
OUT = DATA_DIR / "feature_dictionary.md"

# name -> (group, what it measures, the sentence a user will be shown)
D: dict[str, tuple[str, str, str]] = {
    # --- sender -------------------------------------------------------------
    "sender_reply_to_mismatch": ("Sender", "Reply-To is a different registrable domain than From.", "Replies to this message would go to a different company than the one it appears to be from."),
    "sender_is_freemail": ("Sender", "From domain is a free consumer mail provider.", "This was sent from a free personal email account rather than a company domain."),
    "sender_domain_length": ("Sender", "Character length of the sending domain.", "The sending domain is unusually long."),
    "sender_domain_digit_count": ("Sender", "Digits in the sending domain.", "The sending domain contains digits, which is uncommon for established brands."),
    "sender_domain_hyphen_count": ("Sender", "Hyphens in the sending domain.", "The sending domain contains hyphens, often used to mimic a real brand name."),
    "sender_domain_subdomain_depth": ("Sender", "Subdomain levels below the registrable domain.", "The sending address uses several subdomain levels."),
    "sender_domain_suspicious_tld": ("Sender", "Sending domain uses a cheap or widely abused suffix.", "The sender's domain uses an address suffix frequently used for throwaway registrations."),
    "sender_display_contains_email": ("Sender", "Display name itself contains an @ address.", "The sender's display name is written to look like an email address."),
    "sender_display_nonascii": ("Sender", "Display name contains non-ASCII characters.", "The sender's name uses characters that can be used to imitate ordinary letters."),
    "brand_claimed_in_display_or_subject": ("Sender", "A known brand is named in the display name or subject.", "This message names a well-known company."),
    "brand_claimed_but_sender_unrelated": ("Sender", "A brand is claimed but the sending domain is unrelated to it.", "This message claims to be from a well-known company, but it was not sent from that company's domain."),
    # --- links --------------------------------------------------------------
    "link_count": ("Links", "Number of links (log scale).", "This message contains an unusual number of links."),
    "distinct_link_domain_count": ("Links", "Number of distinct destination domains (log scale).", "The links in this message point to several different websites."),
    "link_display_mismatch_count": ("Links", "Links whose visible text names a different domain than the destination (log scale).", "Several links display one website address while actually going to another."),
    "has_link_display_mismatch": ("Links", "At least one display/destination mismatch.", "A link displays one website address but actually goes to a different one."),
    "link_domain_matches_sender": ("Links", "At least one link goes to the sender's own domain.", "At least one link goes to the same company that sent the message."),
    "no_link_matches_sender_domain": ("Links", "Message has links, none to the sender's domain.", "None of the links go to the company this message appears to be from."),
    "has_ip_literal_link": ("Links", "A link points at a bare IP address.", "A link points directly at a numeric internet address instead of a domain name."),
    "has_punycode_link": ("Links", "A link host uses punycode (xn--).", "A link uses an internationalised domain that can be made to look like a familiar name."),
    "has_url_shortener": ("Links", "A link uses a known URL shortener.", "A link uses a shortening service, which hides the real destination."),
    "has_suspicious_tld_link": ("Links", "A link domain uses a cheap or widely abused suffix.", "A link points to a domain with an address suffix frequently used for throwaway registrations."),
    "has_userinfo_in_url": ("Links", "A URL contains an @ before the host.", "A link is formatted so the part before the @ looks like a familiar website, while the real destination comes after it."),
    "max_url_length": ("Links", "Longest URL (log scale).", "This message contains an unusually long web address."),
    "max_subdomain_depth": ("Links", "Deepest subdomain nesting across links.", "A link uses deeply nested subdomains, which can push a familiar name to the left of the real domain."),
    "has_http_only_link": ("Links", "At least one link uses unencrypted http.", "A link uses an unencrypted connection."),
    "brand_name_in_link_subdomain": ("Links", "A brand name appears in the subdomain rather than the registrable domain.", "A link puts a well-known company's name in the subdomain, while the actual site belongs to someone else."),
    # --- structure ----------------------------------------------------------
    "body_word_count": ("Structure", "Words in the body (log scale).", "The message body is unusually short or long."),
    "body_is_very_short": ("Structure", "Fewer than 20 words of body text.", "The message says very little, relying on a link or an image instead."),
    "link_density_per_100_words": ("Structure", "Links per 100 words of body text.", "This message is mostly links with very little text around them."),
    "attachment_count": ("Structure", "Number of attachments (log scale).", "This message carries attachments."),
    "has_risky_attachment": ("Structure", "An attachment uses an executable or archive extension.", "This message carries an attachment of a type commonly used to deliver malware."),
    # --- language -----------------------------------------------------------
    "urgency_term_count": ("Language", "Distinct urgency phrases found.", "The message pressures you to act immediately."),
    "threat_term_count": ("Language", "Distinct threat or account-status phrases found.", "The message warns that your account is suspended, locked, or at risk."),
    "credential_term_count": ("Language", "Distinct credential or sign-in phrases found.", "The message asks you to sign in, verify your identity, or confirm account details."),
    "financial_term_count": ("Language", "Distinct payment or money phrases found.", "The message refers to payments, invoices, or money."),
    "has_generic_greeting": ("Language", "Opens with a generic greeting rather than a name.", "The message greets you generically instead of by name."),
    "subject_length": ("Language", "Characters in the subject line.", "The subject line is unusually long."),
    "subject_is_empty": ("Language", "Subject line is empty.", "This message has no subject line."),
    "subject_exclamation_count": ("Language", "Exclamation marks in the subject.", "The subject line uses exclamation marks for emphasis."),
    "subject_allcaps_word_count": ("Language", "Words in all capitals in the subject.", "The subject line shouts in capital letters."),
    "subject_nonascii": ("Language", "Subject contains non-ASCII characters.", "The subject line uses non-standard characters."),
    "subject_has_reply_prefix": ("Language", "Subject starts with Re:, Fwd: or Fw:.", "The subject is formatted as a reply or forward."),
    "body_allcaps_ratio": ("Language", "Proportion of all-capital words in the body.", "Much of the message is written in capital letters."),
}

AVAILABILITY_NOTE = {}  # all features below are available at inference time by design


def main() -> int:
    if not REPORT.exists():
        print("Run build_dataset.py first.", file=sys.stderr)
        return 1
    r = json.loads(REPORT.read_text(encoding="utf-8"))
    sep = r["feature_separation_phish_vs_legit"]
    auc = r["single_feature_auc"]
    era = r["feature_separation_spam_vs_ham_same_era_control"]
    prev = r["feature_prevalence_pct_nonzero"]
    suspect = set(r["suspected_corpus_artifacts"])
    flat = set(r["features_with_no_separation"])
    order = [n for n, _ in sorted(sep.items(), key=lambda kv: -kv[1]["abs_gap"])]

    L: list[str] = []
    A = L.append
    A("# Feature Data Dictionary")
    A("")
    A("**Deliverable #8 · WBS 1.4 and 1.5.** Every input the PhishLens model receives.")
    A(f"Connor Schell · CYBR 498W · generated {r['generated_utc']} from "
      f"`01_Data/processed/splits/dataset_report.json`")
    A("")
    A(f"**{r['feature_count']} features** over **{r['totals']['all']:,} messages** "
      f"({r['totals']['train']:,} train / {r['totals']['test']:,} test).")
    A("")
    A("Regenerate with `python 01_Data/src/build_dataset.py && "
      "python 01_Data/src/make_feature_dictionary.py`. The prose is written by hand; "
      "every number is read from the dataset report, so the two cannot drift apart.")
    A("")
    A("---")
    A("")
    A("## How to read this")
    A("")
    A("- **Phish mean / Legit mean** — average value of the feature in each class. "
      "Binary features read as a proportion: 0.95 means 95% of messages have it.")
    A("- **AUC** — how well the feature alone separates the classes. 0.5 is useless; "
      "far from 0.5 either way means one feature nearly does the job on its own, which on this "
      "corpus is a reason for suspicion before it is a reason for confidence.")
    A("- **Same-era gap** — the control. Average difference between *spam and ham*, which both "
      "come from the SpamAssassin corpus and the same year. See the warning below.")
    A("- **Explanation shown to the user** — the sentence WBS 2.3 will display when this "
      "feature contributes materially to a verdict. Every feature has one. That is the "
      "design constraint: a feature nobody can explain does not belong in this model.")
    A("")
    A("## The warning that matters")
    A("")
    A("The phishing messages are from 2022 onward. The legitimate and spam messages are from "
      "2002. **Any feature that tracks the era of an email rather than its intent will appear "
      "to separate the classes almost perfectly while telling us nothing about phishing.**")
    A("")
    A("The spam-vs-ham column is the control for this. Spam and ham share a source and a year, "
      "so a feature that also separates them is doing real work. A feature that separates only "
      "across the corpora is suspect.")
    A("")
    if suspect:
        A(f"**{len(suspect)} features have a single-feature AUC far enough from 0.5 to warrant "
          f"review:** "
          + ", ".join(f"`{n}`" for n in sorted(suspect)) + ".")
        A("")
        A("These are kept rather than deleted, because some may be genuine — phishing really "
          "does use longer URLs and more digits in domains. The obligation is on the evaluation: "
          "**WBS 2.1 must report precision, recall and false-positive rate twice — once with the "
          "full feature set and once with these ablated.** If the numbers barely move, the "
          "features were honest. If they collapse, the model was reading the calendar. That "
          "comparison belongs in the final report either way.")
        A("")
    A("The durable fix is a modern legitimate-mail corpus, which would remove the era gap at "
      "source. That is recorded as a risk rather than scheduled work, because it would mean "
      "re-running WBS 1.1 and there is no obvious freely redistributable source of recent "
      "ordinary inbox mail.")
    A("")
    A("## Rules every feature obeys")
    A("")
    A("1. **Individually explainable.** Each feature maps to one sentence a person would accept "
      "as a reason. There are no bag-of-words or embedding dimensions, because a contribution "
      "from one cannot be explained, and explanation is the point of this project.")
    A("2. **Available at inference time.** The extension reads Gmail's rendered page. It never "
      "sees the Received chain, Return-Path, or Authentication-Results, so no feature uses them. "
      "A test asserts this.")
    A("3. **No corpus identity.** Recipient address, date, and Message-ID are excluded. The "
      "phishing corpus anonymises every recipient to `phishing@pot` and is 20 years newer than "
      "the rest, so any of those would separate the classes perfectly and learn nothing. A test "
      "asserts this too.")
    A("4. **Properties, not identities.** The sending domain is used to ask whether it matches a "
      "link domain, never as a value itself. One-hot encoding domains would memorise the corpus.")
    A("")
    A("## Known limitation: language")
    A("")
    A("The urgency, threat, credential, and financial word lists are English only. The phishing "
      "corpus contains German, Portuguese, and other non-English samples, which will score low "
      "on all four regardless of content. Expect lower recall on non-English phishing, and "
      "expect `subject_nonascii` to carry weight it has not earned. Language detection, or "
      "per-language word lists, is the obvious extension and is out of scope this semester.")
    A("")
    A("---")
    A("")
    A("## The features")
    A("")
    for group in ("Sender", "Links", "Structure", "Language"):
        names = [n for n in order if D.get(n, ("", "", ""))[0] == group]
        if not names:
            continue
        A(f"### {group}")
        A("")
        A("| Feature | Measures | Phish | Legit | AUC | Same-era gap | Flag |")
        A("|---|---|---|---|---|---|---|")
        for n in names:
            g, measures, _ = D[n]
            s, e = sep[n], era[n]
            flag = "artifact?" if n in suspect else ("flat" if n in flat else "")
            A(f"| `{n}` | {measures} | {s['phish_mean']} | {s['legit_mean']} | "
              f"{auc[n]} | {e['abs_gap']} | {flag} |")
        A("")
        A("**Explanations shown to the user:**")
        A("")
        for n in names:
            A(f"- `{n}` — \"{D[n][2]}\"")
        A("")
    A("---")
    A("")
    A("## Features with no measured separation")
    A("")
    if flat:
        A("These show almost no difference between classes in this corpus. They are kept "
          "because most are rare-but-decisive signals: a punycode link or an executable "
          "attachment is strong evidence when it appears, and prevalence this low simply means "
          "it rarely appears. `body_allcaps_ratio` has no such defence and is the first "
          "candidate for removal if the model needs trimming.")
        A("")
        A("| Feature | % of phishing with it | % of legitimate with it |")
        A("|---|---|---|")
        for n in sorted(flat):
            A(f"| `{n}` | {prev[n]['phish_pct']}% | {prev[n]['legit_pct']}% |")
        A("")
    A("## Dataset and split")
    A("")
    A(f"- Split: **{int((1 - r['test_size']) * 100)}/{int(r['test_size'] * 100)}**, "
      f"stratified on the three-way label, seed `{r['seed']}`.")
    A(f"- Phishing share: **{r['binary_balance']['train_phish_pct']}%** of train, "
      f"**{r['binary_balance']['test_phish_pct']}%** of test.")
    A(f"- Leakage: **{r['leakage']['shared_record_ids']}** shared record ids, "
      f"**{r['leakage']['shared_fingerprints']}** shared near-duplicate fingerprints. "
      "The build refuses to write a split if either is non-zero.")
    A("")
    A("**The target is binary** — 1 for phishing, 0 for legitimate or spam. The three-way label "
      "rides along as `label_3way` and is never fed to the model; it exists so WBS 2.1 can "
      "report false positives on spam separately from false positives on ordinary mail. That "
      "split is the number that predicts whether the extension is tolerable in daily use.")
    A("")
    A("**Phishing is 54% of this corpus and nothing like that in a real inbox.** Precision and "
      "false-positive rate must be read against a realistic prior, with the class balance stated "
      "next to every metric.")
    A("")
    A("## Class balance")
    A("")
    A("| Split | Phishing | Legitimate | Spam | Total |")
    A("|---|---|---|---|---|")
    for split in ("overall", "train", "test"):
        b = r["class_balance"][split]
        A(f"| {split} | {b.get('phish', {}).get('n', 0):,} | {b.get('ham', {}).get('n', 0):,} | "
          f"{b.get('spam', {}).get('n', 0):,} | {sum(v['n'] for v in b.values()):,} |")
    A("")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(L)} lines)")
    missing = [n for n in sep if n not in D]
    if missing:
        print(f"WARNING - undocumented features: {missing}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
