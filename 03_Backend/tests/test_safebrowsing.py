"""WBS 3.5 regression tests - Safe Browsing lookup, caching, degradation.

No network and no database here. Both are stubbed, which is the point: what
needs proving is that a scan survives every way this signal can fail, and the
failures are exactly the cases that are awkward to produce against the real
service. The live integration is exercised in 05_Deployment (WBS 5.4).

The properties asserted are the ones the design claims:
  - no key means the signal is off, silently
  - a cache hit never reaches the network
  - a lookup failure is not cached, and is not read as "safe"
  - a flagged URL floors severity at dangerous
  - nothing in this path can raise into /scan
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "01_Data" / "src", ROOT / "02_Model"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# isort: off
from app_import import app  # noqa: E402,F401  (registers the "app" package)

import app.services.safebrowsing as sb  # noqa: E402
from app.config import get_settings  # noqa: E402
import explain as explain_mod  # noqa: E402
# isort: on

BAD = "http://ledqer-secure.com/verify"
GOOD = "https://example.edu/notes"


def _record(*urls):
    return SimpleNamespace(links=[SimpleNamespace(url=u) for u in urls], attachments=[])


@pytest.fixture
def keyed(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "safe_browsing_api_key", "test-key", raising=False)
    monkeypatch.setattr(s, "safe_browsing_enabled", True, raising=False)
    return s


@pytest.fixture(autouse=True)
def _no_cache_by_default(monkeypatch):
    """Cache is empty and writes are no-ops unless a test says otherwise."""
    monkeypatch.setattr(sb, "_read_cache", lambda urls: {})
    monkeypatch.setattr(sb, "_write_cache", lambda entries: None)


# ------------------------------------------------------------- key absent --

def test_without_an_api_key_the_signal_is_off_and_silent(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "safe_browsing_api_key", "", raising=False)
    monkeypatch.setattr(sb, "_query_api", lambda urls: pytest.fail("must not call the API"))
    assert sb.check_record(_record(BAD)) == []


def test_disabled_flag_turns_it_off_even_with_a_key(monkeypatch, keyed):
    monkeypatch.setattr(keyed, "safe_browsing_enabled", False, raising=False)
    monkeypatch.setattr(sb, "_query_api", lambda urls: pytest.fail("must not call the API"))
    assert sb.check_record(_record(BAD)) == []


# ------------------------------------------------------------------ hits --

def test_a_flagged_url_produces_one_rule_signal(monkeypatch, keyed):
    monkeypatch.setattr(sb, "_query_api", lambda urls: {BAD: ("SOCIAL_ENGINEERING", 300)})
    out = sb.check_record(_record(BAD))
    assert len(out) == 1
    assert out[0]["kind"] == "rule"
    assert out[0]["rule"] == sb.RULE_NAME
    assert "phishing site" in out[0]["text"]
    assert "ledqer-secure.com" in out[0]["text"]


def test_clean_urls_produce_nothing(monkeypatch, keyed):
    monkeypatch.setattr(sb, "_query_api", lambda urls: {})
    assert sb.check_record(_record(GOOD)) == []


def test_only_one_signal_even_with_several_flagged_links(monkeypatch, keyed):
    second = "http://other-bad.example/x"
    monkeypatch.setattr(sb, "_query_api",
                        lambda urls: {BAD: ("MALWARE", 300), second: ("MALWARE", 300)})
    assert len(sb.check_record(_record(BAD, second))) == 1


def test_urls_per_message_are_bounded(monkeypatch, keyed):
    monkeypatch.setattr(keyed, "safe_browsing_max_urls", 3, raising=False)
    asked = {}
    monkeypatch.setattr(sb, "_query_api", lambda urls: asked.update(n=len(urls)) or {})
    sb.check_record(_record(*[f"https://example.com/{i}" for i in range(25)]))
    assert asked["n"] == 3


def test_non_http_schemes_are_ignored(monkeypatch, keyed):
    monkeypatch.setattr(sb, "_query_api", lambda urls: pytest.fail("must not call the API"))
    assert sb.check_record(_record("mailto:someone@example.com", "javascript:void(0)")) == []


# ----------------------------------------------------------------- cache --

def test_a_cache_hit_does_not_reach_the_network(monkeypatch, keyed):
    monkeypatch.setattr(sb, "_read_cache", lambda urls: {BAD: ("unsafe", "MALWARE")})
    monkeypatch.setattr(sb, "_query_api", lambda urls: pytest.fail("must not call the API"))
    out = sb.check_record(_record(BAD))
    assert len(out) == 1
    assert "malware" in out[0]["text"]


def test_only_cache_misses_are_sent_upstream(monkeypatch, keyed):
    monkeypatch.setattr(sb, "_read_cache", lambda urls: {GOOD: ("safe", None)})
    sent = {}
    monkeypatch.setattr(sb, "_query_api", lambda urls: sent.update(urls=urls) or {})
    sb.check_record(_record(GOOD, BAD))
    assert sent["urls"] == [BAD]


def test_cache_duration_from_the_api_is_what_gets_stored(monkeypatch, keyed):
    written = []
    monkeypatch.setattr(sb, "_write_cache", lambda entries: written.extend(entries))
    monkeypatch.setattr(sb, "_query_api", lambda urls: {BAD: ("MALWARE", 900)})
    sb.check_record(_record(BAD, GOOD))
    by_url = {e[0]: e for e in written}
    assert by_url[BAD][1] == "unsafe" and by_url[BAD][3] == 900
    # Safe verdicts get our own TTL: the API returns no duration for a non-match.
    assert by_url[GOOD][1] == "safe"
    assert by_url[GOOD][3] == get_settings().safe_browsing_safe_ttl_s


def test_google_duration_strings_are_parsed(monkeypatch):
    assert sb._parse_duration("300s", 1) == 300
    assert sb._parse_duration("300.5s", 1) == 300
    assert sb._parse_duration(None, 7) == 7
    assert sb._parse_duration("nonsense", 7) == 7


# ----------------------------------------------------------- degradation --

def test_a_failed_lookup_is_not_cached_and_not_read_as_safe(monkeypatch, keyed):
    """The distinction the design turns on.

    `_query_api` returning None means the question was never answered. Caching
    that as "safe" would disable the signal for the whole TTL on exactly the
    URLs the service could not vouch for.
    """
    written = []
    monkeypatch.setattr(sb, "_write_cache", lambda entries: written.extend(entries))
    monkeypatch.setattr(sb, "_query_api", lambda urls: None)
    assert sb.check_record(_record(BAD)) == []
    assert written == []


def test_an_empty_result_is_a_real_answer_and_is_cached(monkeypatch, keyed):
    """Distinct from the case above: {} means Google answered 'no matches'."""
    written = []
    monkeypatch.setattr(sb, "_write_cache", lambda entries: written.extend(entries))
    monkeypatch.setattr(sb, "_query_api", lambda urls: {})
    sb.check_record(_record(BAD))
    assert [e[1] for e in written] == ["safe"]


@pytest.mark.parametrize("boom", [
    TimeoutError("timed out"),
    ConnectionError("refused"),
    ValueError("malformed json"),
    RuntimeError("anything at all"),
])
def test_no_exception_from_the_lookup_escapes_into_the_scan(monkeypatch, keyed, boom):
    """check_record must absorb a raising helper, not merely a well-behaved one."""
    def explode(urls):
        raise boom
    monkeypatch.setattr(sb, "_query_api", explode)
    assert sb.check_record(_record(BAD)) == []


def test_no_exception_from_the_cache_escapes_into_the_scan(monkeypatch, keyed):
    def explode(urls):
        raise RuntimeError("database gone")
    monkeypatch.setattr(sb, "_read_cache", explode)
    assert sb.check_record(_record(BAD)) == []


def test_a_cache_write_failure_does_not_lose_the_verdict(monkeypatch, keyed):
    """The verdict is already known; failing to cache it must not discard it."""
    def explode(entries):
        raise RuntimeError("disk full")
    monkeypatch.setattr(sb, "_write_cache", explode)
    monkeypatch.setattr(sb, "_query_api", lambda urls: {BAD: ("MALWARE", 300)})
    out = sb.check_record(_record(BAD))
    assert len(out) == 1 and out[0]["rule"] == sb.RULE_NAME


# ------------------------------------------------------------ the floor --

def test_a_flagged_link_floors_severity_at_dangerous():
    """The rule has to change the verdict, not just add a sentence.

    A rule that only decorates the panel is the failure mode the WBS 2.3 note
    on RULE_FLOORS was written about.
    """
    assert explain_mod.RULE_FLOORS[sb.RULE_NAME] == "dangerous"
    rule = {"kind": "rule", "rule": sb.RULE_NAME, "text": "..."}
    severity, floored_by = explain_mod.apply_rule_floor("clear", [rule])
    assert severity == "dangerous"
    assert floored_by == sb.RULE_NAME


def test_the_floor_never_lowers_a_tier():
    rule = {"kind": "rule", "rule": "link_display_mismatch", "text": "..."}
    severity, _ = explain_mod.apply_rule_floor("dangerous", [rule])
    assert severity == "dangerous"


def test_floor_advice_matches_the_tier_it_produced():
    """A confirmed malware link must not be described as merely untrusted."""
    dangerous = explain_mod.rule_floor_advice("dangerous")
    suspicious = explain_mod.rule_floor_advice("suspicious")
    assert dangerous != suspicious
    assert "Do not click" in dangerous
