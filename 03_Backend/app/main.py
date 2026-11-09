"""PhishLens API entrypoint.

WBS 3.3 built /health and /scan. WBS 3.4 adds /register (per-install token
issuance), /feedback (attributable disagreement with a verdict), rate limiting
on all three, and the CORS policy that lets the packaged extension call the API
from its own origin and nothing else.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routes import feedback, health, register, scan

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="PhishLens API",
    description="Explainable phishing detection for the Gmail web client.",
    version="0.3.0",
)

# Rate limiting is per route, as a dependency; see app/ratelimit.py for the
# keying rules and the 429 response.

# CORS (A-02 control table). An empty allowlist means same-origin only, which is
# what the local test page needs; the deployed .env names the published
# extension origin, chrome-extension://<id>, once WBS 4.1 has an id to name.
if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

app.include_router(health.router)
app.include_router(register.router)
app.include_router(scan.router)
app.include_router(feedback.router)

# Testing surface: a page that posts to /scan from the same origin, so no CORS
# policy is needed. Mounted last so it cannot shadow the API routes above.
# Not part of the proposal deliverables - it exists to exercise the API by hand
# and it is the markup WBS 4.3 will reuse for the extension panel.
_STATIC = Path(__file__).resolve().parent / "static"
if _STATIC.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")
