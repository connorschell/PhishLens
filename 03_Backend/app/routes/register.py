"""WBS 3.4 - POST /register.

Mints one per-install token at first run. Rate limited per source IP rather
than per install, because the caller has no install yet; this is the bound on
mass minting named in 00_Admin/auth-design-revision.md.

The token store is the database, so unlike /scan this endpoint has no degraded
mode: with no database there is nothing to register against, and returning a
token that cannot be verified later would be worse than a clear 503.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import issue_install
from ..db import session_scope
from ..ratelimit import register_limit
from ..schemas import RegisterRequest, RegisterResponse

log = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


@router.post("/register", response_model=RegisterResponse,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(register_limit)])
def register(req: RegisterRequest) -> RegisterResponse:
    try:
        with session_scope() as session:
            if session is None:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "registration unavailable: no token store configured")
            install_id, token = issue_install(
                session, req.extension_version, req.client_platform)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("registration failed")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "registration unavailable: token store unreachable") from exc

    # Logged by install id only. The plaintext token is in the response body and
    # nowhere else.
    log.info("issued install %s (%s)", install_id, req.extension_version)
    return RegisterResponse(
        install_id=install_id,
        token=token,
        issued_at=datetime.now(timezone.utc).isoformat(),  # noqa: UP017 (py3.10 runtime)
    )
