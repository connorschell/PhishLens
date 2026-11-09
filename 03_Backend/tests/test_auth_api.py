"""WBS 3.4 regression tests - per-install tokens, rate limiting, feedback.

These run without a database, which is deliberate: the degraded path is the one
most likely to be got wrong, and the properties asserted here are the ones the
design in 00_Admin/auth-design-revision.md actually claims. The claims that need
a live installs table (issuance, revocation, feedback ownership) are exercised
against PostgreSQL in 05_Deployment, WBS 5.4.
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

# isort: off
# app_import must be imported first: it is what registers "app" as a package in
# sys.modules, so every app.* import below depends on it having already run.
# Without the guard, import sorting reorders these and collection fails when
# pytest is invoked from the repository root rather than from 03_Backend.
from app_import import app  # noqa: E402

import app.ratelimit as ratelimit  # noqa: E402
from app.auth import TOKEN_PREFIX, bearer_token, new_token, token_hash  # noqa: E402
from app.config import get_settings  # noqa: E402
# isort: on

client = TestClient(app)
MESSAGE = {"subject": "Re: lab notes", "body_text": "Attached the readings from Tuesday."}


@pytest.fixture(autouse=True)
def _clean_limiter():
    ratelimit.reset()
    yield
    ratelimit.reset()


# ----------------------------------------------------------------- tokens --

def test_tokens_are_random_prefixed_and_not_stored_in_the_clear():
    a, b = new_token(), new_token()
    assert a != b
    assert a.startswith(TOKEN_PREFIX)
    # 32 bytes of entropy, URL-safe encoded.
    assert len(a) - len(TOKEN_PREFIX) >= 40
    assert len(token_hash(a)) == 32
    assert token_hash(a) != token_hash(b)
    assert a.encode() not in token_hash(a)


def test_bearer_parsing_rejects_malformed_headers():
    assert bearer_token("Bearer pl_live_abc") == "pl_live_abc"
    assert bearer_token("bearer pl_live_abc") == "pl_live_abc"
    assert bearer_token("Basic pl_live_abc") is None
    assert bearer_token("pl_live_abc") is None
    assert bearer_token("Bearer   ") is None
    assert bearer_token(None) is None


# ------------------------------------------------------------ enforcement --

def test_scan_without_a_token_is_rejected():
    r = client.post("/scan", json=MESSAGE)
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_scan_with_an_unverifiable_token_still_returns_a_verdict():
    """The degraded path: no token store reachable, so the warning wins.

    A phishing verdict withheld because a database is down is a worse outcome
    than scoring a request whose token could not be checked. Nothing is
    recorded, and the response says so.
    """
    r = client.post("/scan", json=MESSAGE, headers={"Authorization": "Bearer pl_live_whatever"})
    assert r.status_code == 200
    body = r.json()
    assert body["persisted"] is False
    assert body["scan_id"] is None
    assert body["severity"] in {"clear", "caution", "suspicious", "dangerous"}


def test_register_without_a_token_store_fails_loudly():
    """No degraded mode here: a token nothing can verify later is worse than 503."""
    r = client.post("/register", json={"extension_version": "0.1.0"})
    assert r.status_code == 503
    assert "token" in r.json()["detail"].lower()


def test_feedback_requires_a_token_and_never_degrades():
    anon = client.post("/feedback", json={"scan_id": 1, "disagreement": "false_positive"})
    assert anon.status_code == 401

    with_token = client.post(
        "/feedback",
        json={"scan_id": 1, "disagreement": "false_positive"},
        headers={"Authorization": "Bearer pl_live_whatever"})
    # Unattributable feedback is refused rather than stored anonymously.
    assert with_token.status_code == 503


def test_feedback_payload_is_bounded():
    headers = {"Authorization": "Bearer pl_live_whatever"}
    bad_kind = client.post("/feedback", headers=headers,
                           json={"scan_id": 1, "disagreement": "maybe"})
    assert bad_kind.status_code == 422

    long_note = client.post("/feedback", headers=headers,
                            json={"scan_id": 1, "disagreement": "false_positive",
                                  "note": "x" * 900})
    assert long_note.status_code == 422

    bad_id = client.post("/feedback", headers=headers,
                         json={"scan_id": 0, "disagreement": "false_positive"})
    assert bad_id.status_code == 422


# ---------------------------------------------------------- rate limiting --

def test_register_is_rate_limited_per_ip():
    limit = int(get_settings().register_rate_limit.split("/")[0])
    codes = [client.post("/register", json={"extension_version": "0.1.0"}).status_code
             for _ in range(limit + 2)]
    assert codes[-1] == 429
    assert codes.count(429) == 2


def test_a_429_tells_the_client_when_to_come_back():
    limit = int(get_settings().register_rate_limit.split("/")[0])
    for _ in range(limit):
        client.post("/register", json={})
    r = client.post("/register", json={})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_one_install_tripping_its_limit_does_not_affect_another():
    """The property per-install tokens exist to buy (A-02, isolation)."""
    noisy = {"Authorization": "Bearer pl_live_noisy"}
    quiet = {"Authorization": "Bearer pl_live_quiet"}
    limit = int(get_settings().scan_rate_limit.split("/")[0])

    codes = [client.post("/scan", json=MESSAGE, headers=noisy).status_code
             for _ in range(limit + 1)]
    assert codes[-1] == 429
    assert client.post("/scan", json=MESSAGE, headers=quiet).status_code == 200


def test_limits_are_scoped_per_endpoint():
    """Exhausting /register must not consume an install's /scan budget."""
    headers = {"Authorization": "Bearer pl_live_scoped"}
    for _ in range(int(get_settings().register_rate_limit.split("/")[0]) + 1):
        client.post("/register", json={}, headers=headers)
    assert client.post("/scan", json=MESSAGE, headers=headers).status_code == 200


def test_rate_limit_key_is_the_token_hash_not_the_token():
    token = "pl_live_secret_value"
    key = ratelimit.client_key(_request_with(token))
    assert token not in key
    assert key == "install:" + token_hash(token).hex()


def _request_with(token: str):
    from starlette.requests import Request
    scope = {
        "type": "http", "method": "POST", "path": "/scan",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "client": ("127.0.0.1", 1234), "query_string": b"",
    }
    return Request(scope)
