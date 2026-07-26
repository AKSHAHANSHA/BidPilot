FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependency metadata first so the install layer is cached across source edits.
COPY pyproject.toml README.md* ./
RUN python -m pip install --upgrade pip && python -m pip install .

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts

# Uploaded documents are untrusted input; the process that handles them is not root.
RUN useradd --create-home --uid 10001 bidpilot \
    && mkdir -p /app/data/uploads \
    && chown -R bidpilot:bidpilot /app
USER bidpilot

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
