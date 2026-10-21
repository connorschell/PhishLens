"""WBS 3.3 - liveness and readiness.

Reports the model and the database separately, because they fail separately and
a single "ok" would hide which one is down.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..db import database_ok
from ..schemas import HealthResponse
from ..services.scoring import ModelUnavailable, get_bundle

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        b = get_bundle()
        loaded, variant, trained = True, b["variant"], b["trained_utc"]
    except ModelUnavailable:
        loaded, variant, trained = False, None, None

    ok, detail = database_ok()
    return HealthResponse(
        status="ok" if loaded else "degraded",
        version="0.2.0",
        model_loaded=loaded,
        model_variant=variant,
        model_trained_utc=trained,
        database=detail if ok else f"unavailable ({detail})",
    )
