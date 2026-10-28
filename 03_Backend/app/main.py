"""PhishLens API entrypoint.

WBS 3.3. /health reports the model and the database; /scan scores a message
scraped from the Gmail page and returns the explanation panel.
/register and /feedback land in WBS 3.4.
"""

import logging

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routes import health, scan

logging.basicConfig(level=get_settings().log_level)

app = FastAPI(
    title="PhishLens API",
    description="Explainable phishing detection for the Gmail web client.",
    version="0.2.0",
)

app.include_router(health.router)
app.include_router(scan.router)

# Testing surface: a page that posts to /scan from the same origin, so no CORS
# policy is needed. Mounted last so it cannot shadow the API routes above.
# Not part of the proposal deliverables - it exists to exercise the API by hand
# and it is the markup WBS 4.3 will reuse for the extension panel.
_STATIC = Path(__file__).resolve().parent / "static"
if _STATIC.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="static")
