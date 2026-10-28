"""WBS 2.2/2.3 regression tests.

The explainability claim is testable, so it is tested: if contributions ever
stop reconstructing the score, every sentence the panel shows becomes a story
about the model rather than a report of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "02_Model"))
sys.path.insert(0, str(ROOT / "01_Data" / "src"))

from contributions import load_bundle, score_features, severity_tier, verify_decomposition
from explain import HEADLINES, TEMPLATES, explain

SPLITS = ROOT / "01_Data" / "processed" / "splits"


@pytest.fixture(scope="module")
def bundle():
    return load_bundle("full")


@pytest.fixture(scope="module")
def test_rows():
    return [json.loads(line) for line in (SPLITS / "test.jsonl").open(encoding="utf-8")]


def test_contributions_reconstruct_the_score(bundle, test_rows):
    for row in test_rows[:400]:
        verify_decomposition(score_features(bundle, row["features"]))


def test_probability_matches_a_direct_forward_pass(bundle, test_rows):
    import math
    for row in test_rows[:200]:
        res = score_features(bundle, row["features"])
        logit = bundle["intercept"] + sum(
            bundle["coef"][i] * ((row["features"][n] - bundle["mean"][i]) / bundle["std"][i])
            for i, n in enumerate(bundle["feature_names"]))
        assert res["probability"] == pytest.approx(1 / (1 + math.exp(-logit)), abs=1e-12)


def test_missing_feature_is_an_error_not_a_zero(bundle, test_rows):
    broken = dict(test_rows[0]["features"])
    broken.pop(bundle["feature_names"][0])
    with pytest.raises(KeyError):
        score_features(bundle, broken)


def test_every_model_feature_has_a_template(bundle):
    missing = [n for n in bundle["feature_names"] if n not in TEMPLATES]
    assert not missing, f"features with no explanation template: {missing}"


def test_severity_tiers_are_monotone(bundle):
    t = bundle["severity_tiers"]
    assert t["caution"] <= t["suspicious"] <= t["dangerous"]
    assert severity_tier(0.0, bundle) == "clear"
    assert severity_tier(1.0, bundle) == "dangerous"


def test_shares_sum_to_one_over_positive_contributions(bundle, test_rows):
    for row in test_rows[:200]:
        res = score_features(bundle, row["features"])
        shares = [c["share"] for c in res["toward_phishing"]]
        if shares:
            assert sum(shares) == pytest.approx(1.0, abs=1e-9)


def test_explanations_are_produced_without_a_record(bundle, test_rows):
    """The rule layer needs the parsed message; the model layer must not."""
    for row in test_rows[:100]:
        panel = explain(None, row["features"], bundle)
        assert panel["severity"] in {"clear", "caution", "suspicious", "dangerous"}
        assert 0 <= panel["risk_score"] <= 100
        for s in panel["signals"]:
            assert s["text"].strip().endswith(".")


def test_a_clear_verdict_never_carries_a_dangerous_headline(bundle, test_rows):
    for row in test_rows[:300]:
        panel = explain(None, row["features"], bundle)
        if panel["severity"] == "clear":
            assert panel["signals"] == [] or all(s["share"] >= 0.02 for s in panel["signals"]
                                                 if s["kind"] == "model")


# --------------------------------------------------------------------------- #
# WBS 2.3 - the rule layer must move the verdict, not just the sentence list.
#
# These exist because a scan on the deployed stack returned risk_score 17 and
# severity "clear" while the rule layer had already reported, at rank 0, that a
# link reading "ledger.com/verify" opened ledqer-secure.com. The sentence was
# shown under the headline "Nothing notable found". The module docstring claimed
# rules "always surface ... whatever the model thought"; the code only surfaced
# them in the display. Change Log #15.
# --------------------------------------------------------------------------- #
from types import SimpleNamespace

from explain import (RULE_FLOOR_ADVICE, RULE_FLOOR_HEADLINE, RULE_FLOORS,
                     TIER_ORDER, apply_rule_floor)


def _neutral_features(bundle):
    """A feature vector the model finds unremarkable, so the tier comes out low."""
    return {name: 0.0 for name in bundle["feature_names"]}


def _record_with_spoofed_link():
    link = SimpleNamespace(display_mismatch=True, display_text="ledger.com/verify",
                           registered_domain="ledqer-secure.com", host="ledqer-secure.com")
    return SimpleNamespace(links=[link], attachments=[])


def _record_clean():
    return SimpleNamespace(links=[], attachments=[])


def test_a_fired_rule_raises_the_tier(bundle):
    """The exact model tier here depends on the trained bundle; what matters is
    that it sits below the floor and that the floor is what the user is shown."""
    panel = explain(_record_with_spoofed_link(), _neutral_features(bundle), bundle)
    floor = RULE_FLOORS["link_display_mismatch"]
    assert TIER_ORDER.index(panel["model_severity"]) < TIER_ORDER.index(floor)
    assert panel["severity"] == floor
    assert panel["severity_floored_by"] == "link_display_mismatch"


def test_the_floored_panel_does_not_claim_nothing_is_wrong(bundle):
    panel = explain(_record_with_spoofed_link(), _neutral_features(bundle), bundle)
    assert panel["headline"] == RULE_FLOOR_HEADLINE
    assert panel["headline"] != HEADLINES["clear"]
    assert panel["advice"] == RULE_FLOOR_ADVICE


def test_the_floor_leaves_risk_score_alone(bundle):
    """The score stays the model's output. Only the tier moves."""
    feats = _neutral_features(bundle)
    clean = explain(_record_clean(), feats, bundle)
    floored = explain(_record_with_spoofed_link(), feats, bundle)
    assert floored["risk_score"] == clean["risk_score"]
    assert floored["probability"] == clean["probability"]


def test_no_rule_means_the_model_decides_alone(bundle):
    panel = explain(_record_clean(), _neutral_features(bundle), bundle)
    assert panel["severity_floored_by"] is None
    assert panel["severity"] == panel["model_severity"]
    assert panel["headline"] == HEADLINES[panel["severity"]]


def test_the_floor_never_lowers_a_tier():
    for rule, floor in RULE_FLOORS.items():
        raised, by = apply_rule_floor("dangerous", [{"rule": rule}])
        assert raised == "dangerous", f"{rule} lowered a dangerous verdict"
        assert by is None


def test_the_highest_floor_wins_when_several_rules_fire():
    rules = [{"rule": "link_display_mismatch"}, {"rule": "risky_attachment"}]
    raised, by = apply_rule_floor("clear", rules)
    assert TIER_ORDER.index(raised) >= TIER_ORDER.index("suspicious")
    assert by in RULE_FLOORS


def test_every_floor_names_a_real_tier():
    for rule, floor in RULE_FLOORS.items():
        assert floor in TIER_ORDER, f"{rule} floors to an unknown tier {floor}"
