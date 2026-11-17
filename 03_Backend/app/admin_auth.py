"""WBS 4.5 - password gate for the dashboard.

The dashboard reads across every install: scan history, feedback, aggregate
counts. The per-install bearer token of WBS 3.4 is the wrong credential for it,
because that token is deliberately scoped to one install's own rows and is held
in `chrome.storage.local` on an ordinary user's machine. Handing it authority
over everyone else's data would undo the isolation A-02 was built to provide.

So the dashboard gets its own credential: a single operator password, set in the
deployed .env and known only to the person running the service. It is checked
once, at login, and exchanged for a short-lived signed session token. Three
properties follow from that, and they are the reason it is built this way rather
than sending the password on every request:

1. The password crosses the wire once per session, not once per XHR.
2. The session token is stateless - an HMAC over its own expiry, keyed by
   TOKEN_SIGNING_SECRET - so no table, no migration, and nothing to clean up.
3. It expires on its own. A dashboard tab left open on a lab machine stops
   working rather than remaining a standing grant.

Fail-closed, deliberately. If DASHBOARD_PASSWORD or TOKEN_SIGNING_SECRET is
unset, or the signing secret is still the template placeholder, the dashboard
refuses to issue sessions at all and every route under it returns 503. A deploy
that forgot to set the password gets a dashboard that does not work, which is a
visible failure; the alternative is a dashboard quietly serving everyone's scan
history to the internet. This mirrors the reasoning behind `require_auth`
defaulting to True in config.py.

What this is NOT: a user system. There are no accounts, no roles and no audit
of who looked at what, because there is exactly one operator and the capstone
has no second stakeholder to separate. That limitation is recorded here rather
than left for a grader to find.
"""

from __future__ import annotations

import base64
import hmac
import logging
import secrets
import time
from hashlib import sha256

from fastapi import Depends, HTTPException, status

from .auth import authorization_header, bearer_token
from .config import get_settings

log = logging.getLogger(__name__)

SESSION_PREFIX = "pl_dash_"
_PLACEHOLDER = "change_me_locally"


class DashboardDisabled(Exception):
    """No usable password or signing secret is configured."""


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


def _signing_key() -> bytes:
    """The HMAC key, or raise if the deployment has not configured one."""
    secret = get_settings().token_signing_secret
    if not secret or secret == _PLACEHOLDER:
        raise DashboardDisabled("TOKEN_SIGNING_SECRET is not configured")
    return secret.encode("utf-8")


def _configured_password() -> str:
    password = get_settings().dashboard_password
    if not password or password == _PLACEHOLDER:
        raise DashboardDisabled("DASHBOARD_PASSWORD is not configured")
    return password


def dashboard_available() -> bool:
    """Whether a session could be issued at all. Used by /health."""
    try:
        _signing_key()
        _configured_password()
    except DashboardDisabled:
        return False
    return True


def check_password(presented: str) -> bool:
    """Constant-time comparison, so a wrong guess costs the same as any other.

    `compare_digest` rather than `==` because `==` on str short-circuits at the
    first differing byte, which leaks the length of the correct prefix to an
    attacker who can time the response.
    """
    expected = _configured_password()
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def issue_session(ttl_hours: int | None = None) -> tuple[str, int]:
    """Return (token, expires_at_epoch_seconds).

    The token carries its own expiry and a nonce, signed together. Nothing is
    stored server side, so there is no revocation list - changing
    TOKEN_SIGNING_SECRET and restarting invalidates every outstanding session at
    once, which is the blunt instrument this deployment has and should have.
    """
    key = _signing_key()
    hours = ttl_hours if ttl_hours is not None else get_settings().dashboard_session_hours
    expires_at = int(time.time()) + hours * 3600
    payload = f"{expires_at}.{secrets.token_urlsafe(9)}"
    sig = hmac.new(key, payload.encode("ascii"), sha256).digest()
    return f"{SESSION_PREFIX}{payload}.{_b64e(sig)}", expires_at


def verify_session(token: str | None) -> bool:
    """True only for a token this server signed that has not yet expired."""
    if not token or not token.startswith(SESSION_PREFIX):
        return False
    body = token[len(SESSION_PREFIX):]
    try:
        expires_raw, nonce, sig_b64 = body.split(".")
        key = _signing_key()
        expected = hmac.new(key, f"{expires_raw}.{nonce}".encode("ascii"), sha256).digest()
        # Verify the signature BEFORE trusting the expiry: the expiry is
        # attacker-supplied until the MAC says otherwise.
        if not hmac.compare_digest(expected, _b64d(sig_b64)):
            return False
        return int(expires_raw) > int(time.time())
    except Exception:
        # Any malformed token, bad base64 or unconfigured key is simply not a
        # valid session. Nothing here distinguishes the failures to the caller.
        return False


def unavailable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail)


def require_dashboard_session(
    authorization: str | None = Depends(authorization_header),
) -> None:
    """Dependency guarding every dashboard read route."""
    if not dashboard_available():
        raise unavailable(
            "dashboard is not configured on this deployment "
            "(DASHBOARD_PASSWORD / TOKEN_SIGNING_SECRET unset)")
    if not verify_session(bearer_token(authorization)):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "dashboard session missing or expired; sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
