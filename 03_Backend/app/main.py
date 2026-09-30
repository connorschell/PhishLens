"""PhishLens API entrypoint.

WBS 1.2 scaffold. Only /health exists so the container stack can be brought up
and verified. /scan is added in WBS 3.3; /register and /feedback in WBS 3.4.
"""

from fastapi import FastAPI

app = FastAPI(
    title="PhishLens API",
    description="Explainable phishing detection for the Gmail web client.",
    version="0.1.0",
)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """Liveness probe. Extended in WBS 3.3 to report model and DB status."""
    return {"status": "ok", "version": app.version}
