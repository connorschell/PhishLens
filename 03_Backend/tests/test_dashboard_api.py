"""WBS 4.5 regression tests - dashboard password gate and read endpoints.

Like the WBS 3.4 tests these run without a database, and for the same reason:
what matters most here is the access-control boundary, and that boundary is
enforced before any query runs. The listing and aggregation SQL is exercised
against PostgreSQL in 05_Deployment (WBS 5.4).

The properties asserted are the ones app/admin_auth.py actually claims:
fail-closed when unconfigured, no route readable without a session, a session
token that cannot be forged or back-dated, and an expiry that is honoured.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "01_Data" / "src", ROOT / "02_Model"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# isort: off
from app_import import app  # noqa: E402

import app.admin_auth as admin_auth  # noqa: E402
import app.ratelimit as ratelimit  # noqa: E402
from app.config import get_settings  # noqa: E402
# isort: on

client = TestClient(app)

PASSWORD = "correct-horse-battery-staple"
SECRET = "test-signing-secret-not-the-placeholder"

READ_ROUTES = [
    ("GET", "/dashboard/api/scans"),
    ("GET", "/dashboard/api/feedback"),
    ("GET", "/dashboard/api/metrics"),
    ("POST", "/dashboard/api/feedback/1/review"),
]


@pytest.fixture(autouse=True)
def _clean_limiter():
    ratelimit.reset()
    yield
    ratelimit.reset()


@pytest.fixture
def configured(monkeypatch):
    """A deployment with the dashboard switched on."""
    settings = get_settings()
    monkeypatch.setattr(settings, "dashboard_password", PASSWORD, raising=False)
    monkeypatch.setattr(settings, "token_signing_secret", SECRET, raising=False)
    monkeypatch.setattr(settings, "dashboard_session_hours", 12, raising=False)
    yield settings


@pytest.fixture
def unconfigured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "dashboard_password", "", raising=False)
    monkeypatch.setattr(settings, "token_signing_secret", "", raising=False)
    yield settings


def _session(configured) -> str:
    r = client.post("/dashboard/api/login", json={"password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ------------------------------------------------------------ fail-closed --

def test_unconfigured_dashboard_refuses_to_issue_a_session(unconfigured):
    r = client.post("/dashboard/api/login", json={"password": "anything"})
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]


@pytest.mark.parametrize("method,path", READ_ROUTES)
def test_unconfigured_dashboard_serves_no_data(unconfigured, method, path):
    r = client.request(method, path)
    assert r.status_code == 503


def test_placeholder_secret_is_treated_as_unconfigured(monkeypatch):
    """The .env template ships TOKEN_SIGNING_SECRET=change_me_locally.

    Signing sessions with a value printed in the repository would make the
    session token forgeable by anyone who read the template, so the placeholder
    must count as 'not configured' rather than as a key.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "dashboard_password", PASSWORD, raising=False)
    monkeypatch.setattr(settings, "token_signing_secret", "change_me_locally", raising=False)
    assert admin_auth.dashboard_available() is False
    assert client.post("/dashboard/api/login", json={"password": PASSWORD}).status_code == 503


# ------------------------------------------------------------------ login --

def test_correct_password_issues_a_session(configured):
    r = client.post("/dashboard/api/login", json={"password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token"].startswith(admin_auth.SESSION_PREFIX)
    assert body["expires_at"]


def test_wrong_password_is_rejected_and_leaks_nothing(configured):
    r = client.post("/dashboard/api/login", json={"password": "wrong"})
    assert r.status_code == 401
    # The response must not disclose the real password or its length.
    assert PASSWORD not in r.text
    assert str(len(PASSWORD)) not in r.json()["detail"]


def test_login_is_rate_limited_per_ip(configured, monkeypatch):
    """Brute force bound. The limit is the only thing standing between a weak
    password and an attacker with time, so its absence would be a finding."""
    settings = get_settings()
    monkeypatch.setattr(settings, "dashboard_login_rate_limit", "3/hour", raising=False)
    codes = [client.post("/dashboard/api/login", json={"password": "no"}).status_code
             for _ in range(5)]
    assert 429 in codes
    assert codes.count(401) <= 3


# ---------------------------------------------------------- session token --

@pytest.mark.parametrize("method,path", READ_ROUTES)
def test_routes_reject_a_missing_session(configured, method, path):
    r = client.request(method, path)
    assert r.status_code == 401


@pytest.mark.parametrize("bad", [
    "pl_dash_garbage",
    "pl_dash_9999999999.abc.not-a-signature",
    "Bearer-less-nonsense",
    "",
])
def test_forged_session_tokens_are_rejected(configured, bad):
    r = client.get("/dashboard/api/metrics", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_install_token_is_not_accepted_as_a_dashboard_session(configured):
    """A per-install token must not open the dashboard.

    This is the isolation claim from A-02: the credential a user's browser
    holds grants access to that install's own rows through /scan and
    /feedback, and to nothing else. If it opened the dashboard, every user
    would hold a key to everyone's history.
    """
    from app.auth import new_token
    r = client.get("/dashboard/api/metrics",
                   headers={"Authorization": f"Bearer {new_token()}"})
    assert r.status_code == 401


def test_expired_session_is_rejected(configured):
    token, expires_at = admin_auth.issue_session(ttl_hours=0)
    assert expires_at <= int(time.time())
    assert admin_auth.verify_session(token) is False
    r = client.get("/dashboard/api/metrics", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_session_signed_with_another_key_is_rejected(configured, monkeypatch):
    """Rotating TOKEN_SIGNING_SECRET must invalidate outstanding sessions,
    since that rotation is the only revocation this stateless scheme has."""
    token = _session(configured)
    assert admin_auth.verify_session(token) is True
    monkeypatch.setattr(get_settings(), "token_signing_secret",
                        "a-different-secret-entirely", raising=False)
    assert admin_auth.verify_session(token) is False


def test_expiry_cannot_be_extended_by_editing_the_token(configured):
    """The expiry is inside the MAC, not alongside it."""
    token, _ = admin_auth.issue_session(ttl_hours=1)
    body = token[len(admin_auth.SESSION_PREFIX):]
    expires_raw, nonce, sig = body.split(".")
    forged = f"{admin_auth.SESSION_PREFIX}{int(expires_raw) + 86_400}.{nonce}.{sig}"
    assert admin_auth.verify_session(forged) is False


# ------------------------------------------------- authenticated, no DB --

@pytest.mark.parametrize("method,path", READ_ROUTES)
def test_authenticated_routes_report_503_without_a_database(configured, method, path):
    """Authentication passes, the query cannot run, and the dashboard says so.

    Unlike /scan there is no degraded path here: a dashboard is a convenience
    and a stale or empty page that looked authoritative would be worse than an
    honest failure.
    """
    token = _session(configured)
    r = client.request(method, path, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"]


# ------------------------------------------------------------- the page --

def test_dashboard_page_is_served_and_the_api_is_not_shadowed(configured):
    """The static mount is at '/', so the API router must win on its prefix."""
    page = client.get("/dashboard/")
    assert page.status_code == 200
    assert "Operator dashboard" in page.text
    # The page itself is public markup; it holds no password and no data.
    assert PASSWORD not in page.text
    # And the API below it still requires a session rather than returning HTML.
    assert client.get("/dashboard/api/metrics").status_code == 401
