"""WBS 3.3 - database engine and session handling.

Persistence is deliberately not on the critical path of a scan. If the database
is unreachable, the user still gets their verdict and the response says the scan
was not recorded; a history feature failing is not a reason to withhold a
phishing warning. /health reports the database separately so the failure is
visible rather than silent.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

log = logging.getLogger(__name__)

_engine: Engine | None = None
_Session: sessionmaker | None = None


def get_engine() -> Engine | None:
    global _engine, _Session
    settings = get_settings()
    if not settings.database_url:
        return None
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
        _Session = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session | None]:
    """Yield a session, or None when no database is configured or reachable."""
    if get_engine() is None:
        yield None
        return
    assert _Session is not None
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        log.exception("database write failed; the scan itself was unaffected")
        raise
    finally:
        s.close()


def database_ok() -> tuple[bool, str]:
    engine = get_engine()
    if engine is None:
        return False, "no DATABASE_URL configured"
    try:
        with engine.connect() as cx:
            cx.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:                      # pragma: no cover - env dependent
        return False, f"{type(exc).__name__}: {exc}"[:200]
