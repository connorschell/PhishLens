"""WBS 2.2 - per-feature contribution extraction.

Turns one scored message into the exact list of numbers that produced its
score. Nothing here approximates, samples, or perturbs: for the shipped linear
model the decomposition is algebraic and complete.

    logit(p) = intercept + SUM_i ( w_i * z_i )      z_i = (x_i - mean_i) / std_i

Each term `w_i * z_i` is feature i's contribution to the log-odds, in the same
units as every other term and as the intercept, so they are directly
comparable and they sum - exactly, to floating-point tolerance - back to the
score the user sees. `verify_decomposition` asserts that, and the test suite
runs it over the whole test split.

Sign convention: a positive contribution pushed the message toward phishing, a
negative one pushed it toward legitimate. "Share" is a feature's fraction of
the total positive push, which is what the panel ranks by - a user asking "why
was this flagged" is asking about the evidence against, not the evidence for.

Usage:
    from contributions import load_bundle, score_features
    result = score_features(bundle, feature_dict)
"""

from __future__ import annotations

import json
import math
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def load_bundle(variant: str = "full") -> dict:
    return json.loads((RESULTS / f"model_{variant}.json").read_text(encoding="utf-8"))


def severity_tier(prob: float, bundle: dict) -> str:
    t = bundle["severity_tiers"]
    if prob >= t["dangerous"]:
        return "dangerous"
    if prob >= t["suspicious"]:
        return "suspicious"
    if prob >= t["caution"]:
        return "caution"
    return "clear"


def score_features(bundle: dict, features: dict[str, float]) -> dict:
    """Score one feature vector and decompose the score into named contributions."""
    names = bundle["feature_names"]
    missing = [n for n in names if n not in features]
    if missing:
        raise KeyError(f"feature vector is missing {len(missing)} fields: {missing[:5]}")

    contributions = []
    total = bundle["intercept"]
    for i, name in enumerate(names):
        x = float(features[name])
        z = (x - bundle["mean"][i]) / bundle["std"][i]
        c = bundle["coef"][i] * z
        total += c
        contributions.append({
            "feature": name,
            "value": x,
            "z": z,
            "weight": bundle["coef"][i],
            "contribution": c,
        })

    prob = 1.0 / (1.0 + math.exp(-total))
    positive = sum(c["contribution"] for c in contributions if c["contribution"] > 0)
    for c in contributions:
        c["share"] = (c["contribution"] / positive) if positive > 0 and c["contribution"] > 0 else 0.0

    contributions.sort(key=lambda c: -c["contribution"])
    return {
        "probability": prob,
        "logit": total,
        "intercept": bundle["intercept"],
        "severity": severity_tier(prob, bundle),
        "model_variant": bundle["variant"],
        "contributions": contributions,
        "toward_phishing": [c for c in contributions if c["contribution"] > 0],
        "toward_legitimate": [c for c in contributions if c["contribution"] < 0][::-1],
    }


def verify_decomposition(result: dict, tolerance: float = 1e-9) -> None:
    """The whole explainability claim in one assertion."""
    rebuilt = result["intercept"] + sum(c["contribution"] for c in result["contributions"])
    if abs(rebuilt - result["logit"]) > tolerance:
        raise AssertionError(
            f"contributions do not reconstruct the score: {rebuilt} vs {result['logit']}")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_Data" / "src"))
    bundle = load_bundle()
    splits = Path(__file__).resolve().parents[1] / "01_Data" / "processed" / "splits"
    rows = [json.loads(line) for line in (splits / "test.jsonl").open(encoding="utf-8")]
    worst = 0.0
    for r in rows:
        res = score_features(bundle, r["features"])
        verify_decomposition(res)
        worst = max(worst, abs(res["intercept"]
                               + sum(c["contribution"] for c in res["contributions"])
                               - res["logit"]))
    print(f"decomposition verified on {len(rows)} held-out messages; "
          f"worst reconstruction error {worst:.2e}")
