# PhishLens API image (WBS 1.2 scaffold; used by WBS 3 and 5)
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for lxml / psycopg, removed after install to keep the image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libxml2-dev libxslt1-dev libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && apt-get purge -y build-essential && apt-get autoremove -y

# Run as a non-root user - hardening carried through to WBS 5.1.
RUN useradd --create-home --uid 10001 phishlens
COPY --chown=phishlens:phishlens 03_Backend/ /app/03_Backend/
COPY --chown=phishlens:phishlens 01_Data/src/ /app/01_Data/src/
COPY --chown=phishlens:phishlens 02_Model/ /app/02_Model/
USER phishlens

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "03_Backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
