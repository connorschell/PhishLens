"""WBS 1.4 - the feature extractor.

Turns an EmailRecord into a fixed vector of named, individually meaningful
numbers. Everything downstream depends on the design rules below.

RULE 1 - every feature must be explainable on its own.
    The whole project is explanations tied to real model contributions
    (WBS 2.2/2.3). A contribution is only useful if the feature it belongs to
    can be stated in one plain sentence: "the visible text of a link named a
    different website than the link actually goes to". A bag-of-words dimension
    cannot be stated that way, so there isn't one here.

RULE 2 - no feature may use a field the Gmail page cannot supply.
    The extension reads the rendered message (WBS 4.2). It never sees the
    Received chain, Return-Path, or Authentication-Results. Training on those
    would produce a model that scores well in evaluation and collapses in
    production. They are excluded here and the exclusion is tested.

RULE 3 - no feature may encode which corpus a message came from.
    This is the subtle one, and it is where a project like this quietly fails.
    The phishing corpus anonymises every recipient to `phishing@pot`; the
    SpamAssassin messages are from 2002 while the phishing is from 2022 onward.
    A model given the recipient address or the date would separate the classes
    perfectly, report near-100% precision, and have learned nothing about
    phishing at all. So: no recipient, no date, no Message-ID.

RULE 5 - a feature must be able to VARY on a live Gmail message.
    A feature that is pinned to one value at inference time is worse than
    useless: the model will have learned to rely on it. The MIME-structure
    features (has_html_part, has_text_part, html_without_text_alternative) were
    removed for this reason. They were the three strongest separators in the
    corpus - and they were measuring 2002 plain-text mailing lists against 2022
    HTML phishing, while the extension always supplies both HTML and text, so
    every live message would have scored as phishing. has_list_unsubscribe went
    with them: the Gmail page does not expose the header at all.

RULE 4 - properties, not identities.
    `from_registered_domain` is used to compute *whether* it matches a link
    domain, never as a value in its own right. One-hot encoding domains would
    memorise the corpus rather than learn the pattern.

Usage:
    from features import extract_features, FEATURE_NAMES
    vector = extract_features(record)        # dict: name -> float
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_schema import EmailRecord  # noqa: E402

# --------------------------------------------------------------------------- #
# word lists
#
# Deliberately small and readable. These drive explanations the user will read,
# so each list has to correspond to something a person would recognise as a
# reason. They are English-only - a known limitation, recorded in
# feature_dictionary.md, and visible in the corpus as lower recall on the
# German and Portuguese phishing samples.
# --------------------------------------------------------------------------- #
URGENCY_TERMS = {
    "urgent", "immediately", "act now", "right away", "as soon as possible",
    "expires", "expiring", "expire", "deadline", "last chance", "final notice",
    "within 24 hours", "within 48 hours", "time sensitive", "don't delay",
}
THREAT_TERMS = {
    "suspended", "suspend", "locked", "lock", "disabled", "deactivated",
    "terminated", "unauthorized", "unusual activity", "suspicious activity",
    "security alert", "violation", "restricted", "on hold", "will be closed",
}
CREDENTIAL_TERMS = {
    "password", "log in", "login", "sign in", "signin", "verify your account",
    "confirm your identity", "update your details", "validate your account",
    "security question", "one-time code", "two-factor", "credentials",
}
FINANCIAL_TERMS = {
    "invoice", "payment", "refund", "wire transfer", "bank account",
    "credit card", "billing", "transaction", "balance", "deposit", "tax",
    "bitcoin", "cryptocurrency", "gift card",
}
GENERIC_GREETINGS = {
    "dear customer", "dear user", "dear member", "dear client", "dear sir",
    "dear madam", "dear account holder", "dear valued customer", "hello user",
    "dear friend",
}
FREEMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "mail.ru", "yandex.ru", "protonmail.com", "gmx.com", "icloud.com",
    "live.com", "msn.com", "qq.com", "163.com",
}
SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "ow.ly", "is.gd", "buff.ly",
    "rebrand.ly", "cutt.ly", "shorturl.at", "tiny.cc", "rb.gy", "lnkd.in",
}
# Suffixes repeatedly abused for throwaway registrations. Cheap or free to
# register, so disproportionately present in phishing.
SUSPICIOUS_TLDS = {
    "zip", "mov", "top", "xyz", "tk", "ml", "ga", "cf", "gq", "buzz", "click",
    "link", "work", "country", "kim", "loan", "men", "win", "download", "rest",
}
RISKY_ATTACHMENT_EXTS = {
    "exe", "scr", "js", "jar", "vbs", "ps1", "bat", "cmd", "com", "pif",
    "hta", "iso", "img", "lnk", "docm", "xlsm", "pptm", "zip", "rar", "7z",
}

BRAND_NAMES = {
    "paypal", "microsoft", "apple", "amazon", "google", "netflix", "facebook",
    "instagram", "linkedin", "dhl", "fedex", "ups", "usps", "chase",
    "bankofamerica", "wellsfargo", "hsbc", "barclays", "dropbox", "docusign",
    "adobe", "office365", "outlook", "icloud", "steam", "coinbase", "binance",
}

IP_HOST_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
NONASCII_RE = re.compile(r"[^\x00-\x7F]")
ALLCAPS_RE = re.compile(r"\b[A-Z]{3,}\b")


def _compile_terms(terms: set[str]) -> re.Pattern:
    """Word-boundary matcher for a term set.

    Plain substring matching produced false explanations: "chase" fired on
    "purchase", "ups" on "Yahoo Groups", "lock" on "unblock". Those reach the
    user as a stated reason, so they are correctness bugs, not cosmetics.
    """
    parts = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])", re.IGNORECASE)


_SUFFIX_RE = re.compile(r"(?:ing|ed|es|s)$")


def _family(term: str) -> str:
    """Collapse inflections so one idea is counted once.

    "expire", "expires" and "expiring" in a single sentence is one reason a user
    would accept, not three, and the count feeds an explanation.
    """
    head, _, last = term.lower().rpartition(" ")
    last = _SUFFIX_RE.sub("", last).rstrip("e")
    return f"{head} {last}".strip()


def _count_terms(text: str, matcher: re.Pattern) -> int:
    """How many distinct ideas from the set occur, counted once each."""
    return len({_family(m.group(0)) for m in matcher.finditer(text)})


def _safe_log(value: float) -> float:
    """log1p, so a message with 200 links does not dwarf one with 4."""
    return math.log1p(max(0.0, value))


_URGENCY_TERMS_RE = _compile_terms(URGENCY_TERMS)

_THREAT_TERMS_RE = _compile_terms(THREAT_TERMS)

_CREDENTIAL_TERMS_RE = _compile_terms(CREDENTIAL_TERMS)

_FINANCIAL_TERMS_RE = _compile_terms(FINANCIAL_TERMS)

_GENERIC_GREETINGS_RE = _compile_terms(GENERIC_GREETINGS)

_BRAND_RE = _compile_terms(BRAND_NAMES)

def extract_features(rec: EmailRecord) -> dict[str, float]:
    """Return the full named feature vector for one message."""
    subject = (rec.subject or "").strip()
    subject_lc = subject.lower()
    body = (rec.body_text or "")
    body_lc = body.lower()
    combined = f"{subject_lc} {body_lc}"
    words = body.split()

    sender_domain = rec.from_registered_domain or ""
    sender_label = sender_domain.split(".")[0] if sender_domain else ""
    display_lc = (rec.from_display or "").lower()

    link_domains = [lk.registered_domain for lk in rec.links if lk.registered_domain]
    distinct_domains = set(link_domains)
    hosts = [lk.host for lk in rec.links if lk.host]

    # --- brand impersonation -------------------------------------------------
    # A display name claiming a brand while the sending domain belongs to
    # someone else is the most legible phishing signal there is.
    brand_in_display = {m.group(0).lower() for m in _BRAND_RE.finditer(display_lc)}
    brand_in_subject = {m.group(0).lower() for m in _BRAND_RE.finditer(subject_lc)}
    claimed_brands = brand_in_display | brand_in_subject
    sender_backs_claim = bool(claimed_brands) and any(
        b in sender_domain.replace("-", "").replace(".", "") for b in claimed_brands
    )

    f: dict[str, float] = {}

    # ---------------------------------------------------------------- sender --
    f["sender_reply_to_mismatch"] = float(rec.sender_mismatch)
    f["sender_is_freemail"] = float(sender_domain in FREEMAIL_DOMAINS)
    f["sender_domain_length"] = float(len(sender_domain))
    f["sender_domain_digit_count"] = float(sum(c.isdigit() for c in sender_domain))
    f["sender_domain_hyphen_count"] = float(sender_domain.count("-"))
    # Depth relative to the registrable domain, so bbc.co.uk scores 0 rather
    # than being handed a free point by its two-part suffix.
    _host = (rec.from_domain or "")
    f["sender_domain_subdomain_depth"] = float(
        max(0, _host.count(".") - sender_domain.count(".")) if sender_domain else 0)
    f["sender_domain_suspicious_tld"] = float(
        sender_domain.rsplit(".", 1)[-1] in SUSPICIOUS_TLDS if "." in sender_domain else 0
    )
    f["sender_display_contains_email"] = float("@" in display_lc)
    f["sender_display_nonascii"] = float(bool(NONASCII_RE.search(rec.from_display or "")))
    f["brand_claimed_in_display_or_subject"] = float(bool(claimed_brands))
    f["brand_claimed_but_sender_unrelated"] = float(bool(claimed_brands) and not sender_backs_claim)

    # ----------------------------------------------------------------- links --
    f["link_count"] = _safe_log(rec.link_count)
    f["distinct_link_domain_count"] = _safe_log(rec.distinct_link_domains)
    f["link_display_mismatch_count"] = _safe_log(rec.display_mismatch_count)
    f["has_link_display_mismatch"] = float(rec.display_mismatch_count > 0)
    f["link_domain_matches_sender"] = float(
        bool(sender_domain) and sender_domain in distinct_domains
    )
    f["no_link_matches_sender_domain"] = float(
        rec.link_count > 0 and bool(sender_domain) and sender_domain not in distinct_domains
    )
    f["has_ip_literal_link"] = float(any(IP_HOST_RE.match(h) for h in hosts))
    f["has_punycode_link"] = float(any("xn--" in h for h in hosts))
    f["has_url_shortener"] = float(any(d in SHORTENER_DOMAINS for d in distinct_domains))
    f["has_suspicious_tld_link"] = float(
        any(d.rsplit(".", 1)[-1] in SUSPICIOUS_TLDS for d in distinct_domains if "." in d)
    )
    f["has_userinfo_in_url"] = float(any("@" in lk.url.split("//", 1)[-1].split("/", 1)[0]
                                         for lk in rec.links))
    f["max_url_length"] = _safe_log(max((len(lk.url) for lk in rec.links), default=0))
    f["max_subdomain_depth"] = float(max((h.count(".") for h in hosts), default=0))
    f["has_http_only_link"] = float(any(lk.scheme == "http" for lk in rec.links))
    f["brand_name_in_link_subdomain"] = float(
        any(_BRAND_RE.search(h.rsplit(".", 2)[0]) for h in hosts if h.count(".") >= 2)
    )

    # ------------------------------------------------------------- structure --
    f["body_word_count"] = _safe_log(rec.body_word_count)
    f["body_is_very_short"] = float(rec.body_word_count < 20)
    f["link_density_per_100_words"] = (
        float(rec.link_count) / max(1.0, rec.body_word_count / 100.0)
    ) if rec.body_word_count else float(rec.link_count)
    f["attachment_count"] = _safe_log(rec.attachment_count)
    f["has_risky_attachment"] = float(any(
        (a.filename.rsplit(".", 1)[-1].lower() in RISKY_ATTACHMENT_EXTS)
        for a in rec.attachments if "." in a.filename
    ))

    # ------------------------------------------------------------ linguistic --
    f["urgency_term_count"] = float(_count_terms(combined, _URGENCY_TERMS_RE))
    f["threat_term_count"] = float(_count_terms(combined, _THREAT_TERMS_RE))
    f["credential_term_count"] = float(_count_terms(combined, _CREDENTIAL_TERMS_RE))
    f["financial_term_count"] = float(_count_terms(combined, _FINANCIAL_TERMS_RE))
    f["has_generic_greeting"] = float(_count_terms(body_lc[:400], _GENERIC_GREETINGS_RE) > 0)
    f["subject_length"] = float(len(subject))
    f["subject_is_empty"] = float(not subject)
    f["subject_exclamation_count"] = float(subject.count("!"))
    f["subject_allcaps_word_count"] = float(len(ALLCAPS_RE.findall(subject)))
    f["subject_nonascii"] = float(bool(NONASCII_RE.search(subject)))
    f["subject_has_reply_prefix"] = float(
        subject_lc.startswith(("re:", "fwd:", "fw:"))
    )
    f["body_allcaps_ratio"] = (
        float(len(ALLCAPS_RE.findall(body))) / max(1.0, len(words))
    ) if words else 0.0

    return f


# Fixed order. The model, the dictionary, and the API all index by this.
FEATURE_NAMES: list[str] = list(extract_features(EmailRecord(
    record_id="", source_corpus="", source_group="", source_path="", label="")).keys())

# Fields the extractor must never touch. Rules 2 and 3 above; enforced by tests.
FORBIDDEN_FIELDS = (
    "received_count", "auth_results_present", "return_path_address",  # not in Gmail DOM
    "to_address", "date_iso", "date_raw", "message_id",               # corpus giveaways
    "source_corpus", "source_group", "source_path", "label",          # labels themselves
)


def to_vector(rec: EmailRecord) -> list[float]:
    """Feature values in FEATURE_NAMES order."""
    f = extract_features(rec)
    return [f[name] for name in FEATURE_NAMES]
