"""WBS 3.3 regression tests.

The property that matters most here is not that /scan returns 200. It is that
/scan returns exactly what the model and explanation layer return when called
directly. An API that quietly reshapes, rounds or reorders the explanation would
break the one claim this project makes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "01_Data" / "src", ROOT / "02_Model"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app_import import app, scoring  # noqa: E402  (shim; see conftest.py)

# WBS 3.4 made /scan require a per-install token. These tests run without a
# database, so the token cannot be verified against the installs table; that is
# the degraded path, in which the message is still scored and nothing is
# recorded. The unauthenticated case is asserted in test_auth_api.py.
AUTH = {"Authorization": "Bearer pl_dev_localonly"}
client = TestClient(app, headers=AUTH)

PHISH = {
    "from_display": "LEDGER",
    "from_address": "no-reply@notification.example-wallet.so",
    "subject": "Your account verification has not yet been completed",
    "body_text": ("Dear Users, We are reaching out about an essential security update "
                  "regarding your Wallet. Verify your account now or it will be suspended. "
                  "Confirm your password at the link below."),
    "body_html": ('<p>Verify now: <a href="https://secure-login.example-wallet.so/a/b/c">'
                  'https://www.ledger.com/wallet/device-verify</a></p>'),
    "attachments": [],
}

BENIGN = {
    "from_display": "Liam Bedford",
    "from_address": "lbedford@lbedford.org",
    "subject": "Re: silent pc build",
    "body_text": "On Saturday you asked about fan noise. I ended up using the quieter cooler.",
    "body_html": "<p>On Saturday you asked about fan noise.</p>",
    "attachments": [],
}


def test_health_reports_model_and_database_separately():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["model_loaded"] is True
    assert body["model_variant"] == "full"
    # No database in the test environment, and that must be visible rather than hidden.
    assert "unavailable" in body["database"] or body["database"] == "ok"


def test_scan_returns_a_complete_panel():
    r = client.post("/scan", json=PHISH)
    assert r.status_code == 200
    b = r.json()
    assert 0 <= b["risk_score"] <= 100
    assert b["severity"] in {"clear", "caution", "suspicious", "dangerous"}
    assert b["signals_considered"] == 43
    assert b["headline"] and b["advice"]
    assert b["duration_ms"] >= 0


def test_api_output_matches_calling_the_model_directly():
    """No second implementation, no drift."""
    direct = scoring.score(PHISH)["panel"]
    api = client.post("/scan", json=PHISH).json()
    assert api["risk_score"] == direct["risk_score"]
    assert api["severity"] == direct["severity"]
    assert [s["text"] for s in api["signals"]] == [s["text"] for s in direct["signals"]]
    assert [m["text"] for m in api["mitigating"]] == [m["text"] for m in direct["mitigating"]]


def test_a_plain_message_scores_lower_than_a_phishing_one():
    hi = client.post("/scan", json=PHISH).json()["risk_score"]
    lo = client.post("/scan", json=BENIGN).json()["risk_score"]
    assert lo < hi


def test_missing_database_does_not_fail_the_scan():
    b = client.post("/scan", json=BENIGN).json()
    assert b["persisted"] is False
    assert b["scan_id"] is None


def test_payload_bounds_are_enforced():
    too_long = dict(BENIGN, subject="x" * 2000)
    assert client.post("/scan", json=too_long).status_code == 422

    too_many = dict(BENIGN, attachments=[{"filename": f"{i}.pdf"} for i in range(60)])
    assert client.post("/scan", json=too_many).status_code == 422


def test_empty_message_is_handled_rather_than_crashing():
    r = client.post("/scan", json={})
    assert r.status_code == 200
    assert r.json()["severity"] in {"clear", "caution", "suspicious", "dangerous"}


def test_fingerprint_is_salted_and_stable():
    a = scoring.fingerprint("Subject", "Body")
    b = scoring.fingerprint("Subject", "Body")
    c = scoring.fingerprint("Subject", "Body different")
    assert a == b and a != c and len(a) == 32

    scoring.get_settings.cache_clear()
    import os
    os.environ["FINGERPRINT_SALT"] = "a-different-salt"
    scoring.get_settings.cache_clear()
    assert scoring.fingerprint("Subject", "Body") != a
    del os.environ["FINGERPRINT_SALT"]
    scoring.get_settings.cache_clear()
