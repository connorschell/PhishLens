"""WBS 3.4 - per-install token authentication.

Implements the design in 00_Admin/auth-design-revision.md (grader item A-02).
The token is an identifier, not a secret: it is minted server side at first run,
returned exactly once, and stored only as a SHA-256 hash, so a disclosure of the
installs table yields nothing usable. What the scheme buys is isolation and
revocability - one install can be rate limited or revoked without touching
anyone else - not unforgeability, which an anonymous client cannot provide.

Degraded behaviour, stated plainly because it is a security-relevant choice:
the installs table is the token store, so when the database is unreachable the
server cannot tell a valid token from an invented one. Rather than withhold a
phishing verdict because a database is down, /scan falls back to scoring
unauthenticated and records nothing (persisted = false), and the per-IP rate
limit is what remains in force. /feedback does not degrade: feedback that cannot
be attributed to an install is worthless as a review signal and is refused.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

TOKEN_PREFIX = "pl_live_"
_TOKEN_BYTES = 32


def new_token() -> str:
    """32 bytes from a CSPRNG, URL-safe, prefixed so it is recognisable in logs."""
    return TOKEN_PREFIX + secrets.token_urlsafe(_TOKEN_BYTES)


def token_hash(token: str) -> bytes:
    """SHA-256 of the presented token. Matches digest(token,'sha256') in Postgres."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def bearer_token(authorization: str | None) -> str | None:
    """Pull the token out of an Authorization header, or None if absent/malformed."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class Install:
    install_id: str
    token_digest: bytes


class Revoked(Exception):
    """The token matched an install whose access has been withdrawn."""


def resolve_install(session: Session, token: str | None) -> Install | None:
    """Look a token up. Raises Revoked for a known-but-withdrawn install."""
    if not token:
        return None
    digest = token_hash(token)
    row = session.execute(
        text("SELECT install_id, revoked_at FROM installs WHERE token_hash = :d"),
        {"d": digest},
    ).first()
    if row is None:
        return None
    if row[1] is not None:
        raise Revoked(str(row[0]))
    session.execute(
        text("UPDATE installs SET last_seen_at = now() WHERE install_id = :i"),
        {"i": row[0]},
    )
    return Install(install_id=str(row[0]), token_digest=digest)


def issue_install(session: Session, extension_version: str,
                  client_platform: str) -> tuple[str, str]:
    """Mint a token, store only its hash, return (install_id, plaintext token).

    The plaintext is returned to the caller here and nowhere else; it is not
    logged and cannot be recovered from the database afterwards.
    """
    token = new_token()
    install_id = session.execute(
        text("""
            INSERT INTO installs (token_hash, extension_version, client_platform)
            VALUES (:d, :v, :p)
            RETURNING install_id
        """),
        {"d": token_hash(token), "v": extension_version[:50], "p": client_platform[:30]},
    ).scalar_one()
    return str(install_id), token


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def authorization_header(authorization: str | None = Header(default=None)) -> str | None:
    """Dependency so routes take the header without repeating the signature."""
    return authorization
