FROM python:3.12.8-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.5.24 /uv /uvx /bin/

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY services/api/src ./services/api/src
COPY services/api/migrations ./services/api/migrations
COPY alembic.ini ./

RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python --no-cache --editable ".[dev]" \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app \
    && chown -R app:app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

CMD ["uvicorn", "sawtai.main:app", "--host", "0.0.0.0", "--port", "8000"]
