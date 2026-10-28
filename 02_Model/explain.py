"""WBS 2.3 - explanation templating.

Turns the contribution vector from WBS 2.2 into what the user actually reads:
a severity tier and a short, ranked list of plain-English sentences, each one
tied to a real number the model used.

Two layers, deliberately separate
---------------------------------
MODEL layer. One template per feature. A template is only allowed to state what
its feature measured, in a sentence a non-technical user would accept as a
reason. Ranking is by share of the total push toward phishing - not by raw
weight, which would show the same features on every message. Features whose
value is unremarkable are dropped before templating: a feature can carry a
large weight and still have nothing to say about this particular message.

RULE layer. A small set of deterministic checks that run on the parsed message
itself and always surface when they fire, whatever the model thought. These
exist because a few signals are categorical - a link whose visible text names a
different site than it opens is worth saying out loud even when the model's
other evidence already decided the verdict - and because the rule layer keeps
working if a model version ever regresses.

A fired rule also puts a FLOOR under the severity tier (RULE_FLOORS). Without
it the rule layer is decorative: the sentence appears in the list while the
headline above it still reads "Nothing notable found", which is the state this
code was in until a deployed scan reproduced it. The floor only raises a tier,
never lowers one, and it deliberately does not touch risk_score. The score stays
the model's honest output, so a floored panel reads as what it is - the model
did not flag this, and a direct check did.

No LLM is in this path. Every sentence is a format string over a measured
value, which is what makes the explanation auditable.

Usage:
    from explain import explain
    panel = explain(record, features, bundle)
"""

from __future__ import annotations

from contributions import score_features

MAX_SIGNALS = 6
MIN_SHARE = 0.02          # below this a signal is noise in the ranking
MAX_MITIGATING = 3

HEADLINES = {
    "dangerous": "Strong signs of phishing",
    "suspicious": "Several phishing signs",
    "caution": "A few things look off",
    "clear": "Nothing notable found",
}

TIER_ADVICE = {
    "dangerous": "Do not click links or open attachments in this message.",
    "suspicious": "Treat links and attachments here as untrusted.",
    "caution": "Worth a second look before you act on it.",
    "clear": "No action suggested.",
}

# Tiers, weakest first. Used to compare a model tier against a rule floor.
TIER_ORDER = ["clear", "caution", "suspicious", "dangerous"]

# A fired rule cannot leave the verdict below this tier. These three checks are
# categorical rather than probabilistic: each one is wrong on its own terms, so
# a low model probability is not a reason to stay quiet about it.
RULE_FLOORS = {
    "link_display_mismatch": "suspicious",
    "punycode_link": "suspicious",
    "risky_attachment": "suspicious",
}

# Shown when a rule raised the tier above what the model alone would have said.
# The split has to be explained, because the panel will show a low score beside
# a high tier and that looks like a contradiction until it is named.
RULE_FLOOR_HEADLINE = "A clear warning sign"
RULE_FLOOR_ADVICE = ("The scoring model did not flag this message on its own, but a direct check "
                     "found something that is wrong regardless of the score. Treat links and "
                     "attachments here as untrusted.")


def apply_rule_floor(severity: str, rules: list[dict]) -> tuple[str, str | None]:
    """Raise severity to the highest floor among the rules that fired.

    Returns the resulting tier and the rule that set it, or None if no rule
    raised anything. Never lowers a tier.
    """
    floored_by = None
    for r in rules:
        floor = RULE_FLOORS.get(r.get("rule"))
        if floor is None:
            continue
        if TIER_ORDER.index(floor) > TIER_ORDER.index(severity):
            severity, floored_by = floor, r["rule"]
    return severity, floored_by


def _n(value: float) -> int:
    """Undo the log1p the extractor applied to count-like features."""
    import math
    return int(round(math.expm1(value)))


# --------------------------------------------------------------------------- #
# MODEL layer: one template per feature.
#
# Each entry is (threshold_test, sentence). The threshold test decides whether
# this feature has anything to say about THIS message; the sentence states what
# it measured. Returning None means stay quiet.
# --------------------------------------------------------------------------- #
TEMPLATES = {
    "sender_reply_to_mismatch":
        lambda v, r: "Replies to this message would go to a different address than the one it came from." if v else None,
    "sender_is_freemail":
        lambda v, r: "It was sent from a free personal email service rather than an organisation's own domain." if v else None,
    "sender_domain_length":
        lambda v, r: f"The sending domain is unusually long ({int(v)} characters)." if v >= 20 else None,
    "sender_domain_digit_count":
        lambda v, r: f"The sending domain contains {int(v)} digit{'s' if v != 1 else ''}, which is uncommon for a real organisation." if v >= 1 else None,
    "sender_domain_hyphen_count":
        lambda v, r: f"The sending domain contains {int(v)} hyphen{'s' if v != 1 else ''} - a common way to build a look-alike address." if v >= 1 else None,
    "sender_domain_subdomain_depth":
        lambda v, r: f"The sender's address sits {int(v)} level{'s' if v != 1 else ''} deep in subdomains, which can hide the real owner." if v >= 2 else None,
    "sender_domain_suspicious_tld":
        lambda v, r: "The sending domain uses a top-level domain heavily associated with abuse." if v else None,
    "sender_display_contains_email":
        lambda v, r: "The sender's display name is itself an email address - a trick used to show a different address than the real one." if v else None,
    "sender_display_nonascii":
        lambda v, r: "The sender's display name contains non-standard characters that can imitate ordinary letters." if v else None,
    "brand_claimed_in_display_or_subject":
        lambda v, r: None,          # only meaningful paired with the next one
    "brand_claimed_but_sender_unrelated":
        lambda v, r: "The message presents itself as a well-known company, but it was not sent from that company's domain." if v else None,
    "link_count":
        lambda v, r: f"It contains {_n(v)} links." if _n(v) >= 5 else None,
    "distinct_link_domain_count":
        lambda v, r: f"Its links point to {_n(v)} different websites." if _n(v) >= 3 else None,
    "link_display_mismatch_count":
        lambda v, r: f"{_n(v)} links show one website in their text and open another." if _n(v) >= 1 else None,
    "has_link_display_mismatch":
        lambda v, r: None,          # the count above already says it
    "link_domain_matches_sender":
        lambda v, r: None,          # reassuring only; handled as a mitigating signal
    "no_link_matches_sender_domain":
        lambda v, r: "None of its links lead to the same website the message was sent from." if v else None,
    "has_ip_literal_link":
        lambda v, r: "A link points at a raw IP address instead of a website name." if v else None,
    "has_punycode_link":
        lambda v, r: "A link uses an encoded domain name that can be made to look like a familiar one." if v else None,
    "has_url_shortener":
        lambda v, r: "A link goes through a URL shortener, which hides its real destination." if v else None,
    "has_suspicious_tld_link":
        lambda v, r: "A link points to a top-level domain heavily associated with abuse." if v else None,
    "has_userinfo_in_url":
        lambda v, r: "A link contains an @ before the website name, which makes the real destination the part after it." if v else None,
    "max_url_length":
        lambda v, r: f"Its longest link is {_n(v)} characters, long enough to push the real destination out of view." if _n(v) >= 120 else None,
    "max_subdomain_depth":
        lambda v, r: f"A link's address is {int(v)} levels deep, which can bury the real domain." if v >= 3 else None,
    "has_http_only_link":
        lambda v, r: "A link uses an unencrypted http connection." if v else None,
    "brand_name_in_link_subdomain":
        lambda v, r: "A link puts a company's name in the subdomain of a site that company does not own." if v else None,
    "body_word_count":
        lambda v, r: None,
    "body_is_very_short":
        lambda v, r: "The message body is very short - typical of a message whose only purpose is the link in it." if v else None,
    "link_density_per_100_words":
        lambda v, r: f"It averages {v:.0f} links per 100 words of text." if v >= 5 else None,
    "attachment_count":
        lambda v, r: f"It carries {_n(v)} attachment{'s' if _n(v) != 1 else ''}." if _n(v) >= 1 else None,
    "has_risky_attachment":
        lambda v, r: "An attachment is of a file type that can run code when opened." if v else None,
    "urgency_term_count":
        lambda v, r: f"It uses {int(v)} different urgency phrase{'s' if v != 1 else ''} to push for a fast response." if v >= 1 else None,
    "threat_term_count":
        lambda v, r: f"It raises {int(v)} different consequence{'s' if v != 1 else ''} for not acting - suspension, closure, or similar." if v >= 1 else None,
    "credential_term_count":
        lambda v, r: f"It refers to passwords, sign-in, or account verification in {int(v)} different way{'s' if v != 1 else ''}." if v >= 1 else None,
    "financial_term_count":
        lambda v, r: f"It refers to payment or banking in {int(v)} different way{'s' if v != 1 else ''}." if v >= 1 else None,
    "has_generic_greeting":
        lambda v, r: "It opens with a generic greeting rather than your name." if v else None,
    "subject_length":
        lambda v, r: None,
    "subject_is_empty":
        lambda v, r: "It has no subject line." if v else None,
    "subject_exclamation_count":
        lambda v, r: f"The subject line uses {int(v)} exclamation mark{'s' if v != 1 else ''}." if v >= 1 else None,
    "subject_allcaps_word_count":
        lambda v, r: f"The subject line shouts {int(v)} word{'s' if v != 1 else ''} in capitals." if v >= 1 else None,
    "subject_nonascii":
        lambda v, r: "The subject line contains non-standard characters." if v else None,
    "subject_has_reply_prefix":
        lambda v, r: "The subject is marked as a reply, though no earlier message in the thread exists." if v else None,
    "body_allcaps_ratio":
        lambda v, r: "An unusual share of the message body is in capital letters." if v >= 0.08 else None,
}

MITIGATING = {
    "link_domain_matches_sender": "Its links lead to the same website the message was sent from.",
    "sender_reply_to_mismatch": "Replies would go back to the address it came from.",
    "brand_claimed_but_sender_unrelated": "No company name is being claimed that the sending domain does not back up.",
    "has_generic_greeting": "It does not open with a generic greeting.",
    "urgency_term_count": "It does not push for an urgent response.",
    "threat_term_count": "It does not threaten a consequence for not acting.",
    "credential_term_count": "It does not ask about passwords or account sign-in.",
    "has_link_display_mismatch": "No link shows one website and opens another.",
    "no_link_matches_sender_domain": "At least one link matches the sending domain.",
}


# --------------------------------------------------------------------------- #
# RULE layer: deterministic checks over the parsed message.
# These fire regardless of what the model weighted.
# --------------------------------------------------------------------------- #
def rule_signals(record) -> list[dict]:
    if record is None:
        return []
    out = []
    links = getattr(record, "links", None) or []

    for lk in links:
        if not getattr(lk, "display_mismatch", False):
            continue
        shown = (getattr(lk, "display_text", "") or "").strip()
        real = (getattr(lk, "registered_domain", "") or getattr(lk, "host", "") or "").strip()
        if len(shown) > 60:
            shown = shown[:57] + "..."
        if shown and real:
            out.append({
                "kind": "rule",
                "rule": "link_display_mismatch",
                "text": f"A link reads \"{shown}\" but opens {real}.",
            })
            break

    for lk in links:
        host = (getattr(lk, "host", "") or "")
        if "xn--" in host:
            out.append({"kind": "rule", "rule": "punycode_link",
                        "text": f"The link to {host} uses an encoded domain name that can imitate a familiar one."})
            break

    for a in (getattr(record, "attachments", None) or []):
        name = getattr(a, "filename", "") or ""
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext in {"exe", "scr", "js", "vbs", "jar", "hta", "iso", "lnk", "docm", "xlsm"}:
            out.append({"kind": "rule", "rule": "risky_attachment",
                        "text": f"The attachment \"{name}\" is a file type that can run code when opened."})
            break

    return out


def explain(record, features: dict[str, float], bundle: dict) -> dict:
    """Score a message and return everything the panel needs to render."""
    scored = score_features(bundle, features)

    signals = []
    for c in scored["toward_phishing"]:
        if c["share"] < MIN_SHARE:
            break
        template = TEMPLATES.get(c["feature"])
        if template is None:
            continue
        text = template(c["value"], record)
        if not text:
            continue
        signals.append({
            "kind": "model",
            "feature": c["feature"],
            "text": text,
            "share": round(c["share"], 4),
            "contribution": round(c["contribution"], 4),
        })

    # Rule hits go to the top and are de-duplicated against the model layer.
    rules = rule_signals(record)
    seen = {s["text"] for s in signals}
    rules = [r for r in rules if r["text"] not in seen]
    ranked = rules + signals
    ranked = ranked[:MAX_SIGNALS]

    # The floor is computed from every rule that fired, not only the ones that
    # survived the MAX_SIGNALS truncation - a rule dropped from the display is
    # still a rule that fired.
    severity, floored_by = apply_rule_floor(scored["severity"], rules)

    mitigating = []
    for c in scored["toward_legitimate"]:
        text = MITIGATING.get(c["feature"])
        if text and text not in {m["text"] for m in mitigating}:
            mitigating.append({"feature": c["feature"], "text": text,
                               "contribution": round(c["contribution"], 4)})
        if len(mitigating) >= MAX_MITIGATING:
            break

    return {
        "risk_score": round(scored["probability"] * 100),
        "probability": scored["probability"],
        "severity": severity,
        "headline": RULE_FLOOR_HEADLINE if floored_by else HEADLINES[severity],
        "advice": RULE_FLOOR_ADVICE if floored_by else TIER_ADVICE[severity],
        "model_severity": scored["severity"],
        "severity_floored_by": floored_by,
        "signals": ranked,
        "mitigating": mitigating,
        "model_variant": scored["model_variant"],
        "signals_considered": len(scored["contributions"]),
    }
