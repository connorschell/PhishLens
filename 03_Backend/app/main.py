"""PhishLens API entrypoint.

WBS 3.3. /health reports the model and the database; /scan scores a message
scraped from the Gmail page and returns the explanation panel.
/register and /feedback land in WBS 3.4.
"""

import logging

from fastapi import FastAPI

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
