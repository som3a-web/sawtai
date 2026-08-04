FROM node:22-alpine AS web-build

WORKDIR /web
COPY services/web/package.json services/web/package-lock.json ./
RUN npm ci
COPY services/web/ ./
RUN npm run build

FROM python:3.12.8-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    SAWTAI_STATIC_DIR=/app/static

COPY --from=ghcr.io/astral-sh/uv:0.5.24 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY services/api/src ./services/api/src
COPY services/api/migrations ./services/api/migrations
RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python --no-cache . \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app

COPY --from=web-build /web/dist /app/static
COPY infra/render/start.sh /app/start-render.sh
RUN chown -R app:app /app

USER app
EXPOSE 10000

CMD ["sh", "/app/start-render.sh"]
