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
from explain import TEMPLATES, explain

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
