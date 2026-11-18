"""WBS 3.5 - Google Safe Browsing as one cached, degradable input.

What this adds that nothing else in the system has: a fact about the world
right now. Every other signal is inferred from the message itself - sender
patterns, link-text mismatches, urgency language, structure - and the model
behind them was trained on corpora from 2004-2007. Safe Browsing knows that
this particular URL is serving malware today. A message carrying a link Google
has already flagged should not be judged on its writing style.

HOW THE VERDICT IS USED. Not as a model feature. The bundle was trained on 43
features without this one, so adding a 44th would mean retraining and would
invalidate the per-feature contributions the explanations are built from
(WBS 2.2). It enters as a rule-layer signal instead - the same layer as
link_display_mismatch and punycode_link - which fires regardless of model
probability and puts a floor under the severity tier. Google listing a URL as
malware is categorical in exactly the way that layer is for, and it takes the
strongest floor there is.

CACHING. The url_reputation table (WBS 3.1) is keyed on sha256(url) with an
expires_at. A fresh cache hit never leaves this server. Only misses are sent
upstream, batched into one request. Unsafe verdicts are cached for the
cacheDuration Google returns; safe verdicts get a fixed TTL of their own,
because the API reports only matches - absence of a match IS the safe answer,
and a clean URL can turn malicious later, so it has to expire too.

DEGRADATION. A scan must never fail because this did. No API key, a timeout, an
HTTP error, a malformed response, an unreachable database: every one of them
returns no verdicts and the scan proceeds on the model and the existing rules.
Nothing here raises into /scan. The timeout is deliberately short, because a
person is waiting on a security decision and a slow warning is a worse failure
than a missing third-party signal.

PRIVACY, STATED PLAINLY. The database stores a hash of the URL and never the
URL (schema.sql). But the Lookup API is given full URLs, so addresses the
user received do leave this server and go to Google. That is a real disclosure
and it is recorded here, in 00_Admin/data-handling.md and in the final report
rather than left for a reader to infer. The alternative - the Update API, with
a locally maintained database of hash prefixes - avoids it and is substantially
more work than this project has room for. Documented trade, not an oversight.
"""

from __future__ import annotations

import hashlib
import logging

import httpx
from sqlalchemy import text

from ..config import get_settings
from ..db import session_scope

log = logging.getLogger(__name__)

_ENDPOINT = "https://safebrowsing.googleapis.com/v4/threatMatches:find"

# What the API is asked about. ALL_PLATFORMS and the four threat types are the
# broadest the Lookup API accepts; narrowing them would only mean missing hits.
_THREAT_TYPES = ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE",
                 "POTENTIALLY_HARMFUL_APPLICATION"]

# Human wording per threat type. SOCIAL_ENGINEERING is the phishing one and is
# worded as such: "social engineering" is accurate and means nothing to a user
# deciding whether to click.
_THREAT_TEXT = {
    "MALWARE": "is known to distribute malware",
    "SOCIAL_ENGINEERING": "is a known phishing site",
    "UNWANTED_SOFTWARE": "is known to distribute unwanted software",
    "POTENTIALLY_HARMFUL_APPLICATION": "is known to distribute harmful applications",
}

RULE_NAME = "safe_browsing_unsafe"


def url_hash(url: str) -> bytes:
    """SHA-256 of the URL. Matches the bytea key in url_reputation."""
    return hashlib.sha256(url.encode("utf-8", errors="replace")).digest()


# ------------------------------------------------------------------ cache --

def _read_cache(urls: list[str]) -> dict[str, tuple[str, str | None]]:
    """Return {url: (verdict, threat_type)} for unexpired rows. {} on any failure."""
    if not urls:
        return {}
    by_hash = {url_hash(u): u for u in urls}
    try:
        with session_scope() as session:
            if session is None:
                return {}
            rows = session.execute(
                text("""SELECT url_sha256, verdict, threat_type
                          FROM url_reputation
                         WHERE url_sha256 = ANY(:hashes) AND expires_at > now()"""),
                {"hashes": list(by_hash.keys())},
            ).all()
    except Exception:
        # A cache that cannot be read is a cache miss, not an error. The lookup
        # still works; it just costs an upstream call.
        log.warning("url_reputation cache unreadable; treating as miss", exc_info=True)
        return {}
    return {by_hash[bytes(r[0])]: (r[1], r[2]) for r in rows if bytes(r[0]) in by_hash}


def _write_cache(entries: list[tuple[str, str, str | None, int]]) -> None:
    """Upsert (url, verdict, threat_type, ttl_seconds). Failures are swallowed."""
    if not entries:
        return
    try:
        with session_scope() as session:
            if session is None:
                return
            for url, verdict, threat, ttl in entries:
                session.execute(
                    text("""
                        INSERT INTO url_reputation
                               (url_sha256, verdict, threat_type, checked_at, expires_at)
                        VALUES (:h, :v, :t, now(), now() + make_interval(secs => :ttl))
                        ON CONFLICT (url_sha256) DO UPDATE
                            SET verdict     = EXCLUDED.verdict,
                                threat_type = EXCLUDED.threat_type,
                                checked_at  = EXCLUDED.checked_at,
                                expires_at  = EXCLUDED.expires_at
                    """),
                    {"h": url_hash(url), "v": verdict, "t": threat, "ttl": max(60, ttl)},
                )
    except Exception:
        log.warning("url_reputation cache not written", exc_info=True)


# ----------------------------------------------------------------- lookup --

def _parse_duration(value: str | None, default: int) -> int:
    """Google returns cacheDuration as a string like '300s'."""
    if not value:
        return default
    try:
        return int(float(str(value).rstrip("s")))
    except (TypeError, ValueError):
        return default


def _query_api(urls: list[str]) -> dict[str, tuple[str, int]] | None:
    """Ask Google about these URLs.

    Returns {url: (threat_type, ttl_seconds)} for the unsafe ones - an empty
    dict means every URL came back clean, which is a real answer. None means
    the lookup did not happen and nothing may be concluded from it, including
    that the URLs are safe. The caller must keep those two apart: caching a
    failure as "safe" would silently disable the signal for the TTL.
    """
    settings = get_settings()
    body = {
        "client": {"clientId": "phishlens", "clientVersion": "0.3.0"},
        "threatInfo": {
            "threatTypes": _THREAT_TYPES,
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": u} for u in urls],
        },
    }
    try:
        with httpx.Client(timeout=settings.safe_browsing_timeout_s) as client:
            r = client.post(_ENDPOINT, params={"key": settings.safe_browsing_api_key},
                            json=body)
        if r.status_code != 200:
            log.warning("safe browsing lookup returned %s; signal skipped", r.status_code)
            return None
        matches = r.json().get("matches") or []
    except Exception:
        log.warning("safe browsing lookup failed; signal skipped", exc_info=True)
        return None

    out: dict[str, tuple[str, int]] = {}
    for m in matches:
        url = (m.get("threat") or {}).get("url")
        if not url:
            continue
        ttl = _parse_duration(m.get("cacheDuration"),
                              get_settings().safe_browsing_unsafe_ttl_s)
        out[url] = (m.get("threatType") or "MALWARE", ttl)
    return out


# ------------------------------------------------------------------- api --

def check_record(record) -> list[dict]:
    """Return rule signals for any link in this message that Google flags.

    Always returns a list. Never raises - every failure path yields [], which
    leaves the verdict to the model and the existing rules.

    The guarantee is enforced here rather than inferred from the helpers.
    _read_cache and _query_api each handle their own failures, but a scan must
    not start depending on that staying true: this wrapper is what makes
    "never raises" a property of the function a caller actually calls.
    """
    try:
        return _check_record(record)
    except Exception:
        log.warning("safe browsing check failed; signal skipped", exc_info=True)
        return []


def _check_record(record) -> list[dict]:
    settings = get_settings()
    if not settings.safe_browsing_enabled or not settings.safe_browsing_api_key:
        # The documented default. A deployment without a key simply does not
        # use the signal; it does not fail and it does not warn on every scan.
        return []

    links = getattr(record, "links", None) or []
    urls, seen = [], set()
    for lk in links:
        u = (getattr(lk, "url", "") or "").strip()
        if not u or u in seen or not u.lower().startswith(("http://", "https://")):
            continue
        seen.add(u)
        urls.append(u)
        if len(urls) >= settings.safe_browsing_max_urls:
            # Bounded on purpose: one message must not be able to turn into an
            # unbounded upstream request or an unbounded cache write.
            break
    if not urls:
        return []

    cached = _read_cache(urls)
    misses = [u for u in urls if u not in cached]

    verdicts: dict[str, tuple[str, str | None]] = dict(cached)
    if misses:
        fresh = _query_api(misses)
        if fresh is not None:
            to_write = []
            for u in misses:
                if u in fresh:
                    threat, ttl = fresh[u]
                    verdicts[u] = ("unsafe", threat)
                    to_write.append((u, "unsafe", threat, ttl))
                else:
                    verdicts[u] = ("safe", None)
                    to_write.append((u, "safe", None,
                                     settings.safe_browsing_safe_ttl_s))
            try:
                _write_cache(to_write)
            except Exception:
                # The verdict is already in hand. Failing to remember it costs
                # one upstream call next time; discarding it would suppress a
                # warning about a link we know is malicious.
                log.warning("url_reputation write failed; verdict still applied",
                            exc_info=True)
        # fresh is None: lookup failed. Those URLs stay absent from verdicts and
        # nothing is cached, so the next scan tries again rather than inheriting
        # a verdict that was never obtained.

    out = []
    for u in urls:
        verdict, threat = verdicts.get(u, ("unknown", None))
        if verdict != "unsafe":
            continue
        host = u.split("://", 1)[-1].split("/", 1)[0][:80]
        out.append({
            "kind": "rule",
            "rule": RULE_NAME,
            "text": f"Google Safe Browsing reports that the link to {host} "
                    f"{_THREAT_TEXT.get(threat, 'is known to be dangerous')}.",
        })
        # One signal is enough. A second flagged link adds nothing to the
        # decision and crowds the panel.
        break
    return out
