import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from sawtai.analytics.routes import router as analytics_router
from sawtai.audit.routes import router as audit_router
from sawtai.auth.admin_routes import router as admin_router
from sawtai.auth.routes import router as auth_router
from sawtai.cases.routes import router as cases_router
from sawtai.channels.routes import router as channels_router
from sawtai.config import get_settings
from sawtai.crisis.routes import router as crisis_router
from sawtai.data.routes import router as data_router
from sawtai.database import dispose_engine, engine
from sawtai.ingest.routes import router as ingest_router
from sawtai.logging import configure_logging
from sawtai.rag.routes import router as rag_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    yield
    await dispose_engine()


app = FastAPI(
    title="SawtAI API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(cases_router)
app.include_router(channels_router)
app.include_router(analytics_router)
app.include_router(ingest_router)
app.include_router(crisis_router)
app.include_router(rag_router)
app.include_router(audit_router)
app.include_router(data_router)


@app.get("/api/v1/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health/ready", tags=["ops"])
async def readiness() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}


static_dir = Path(os.environ.get("SAWTAI_STATIC_DIR", Path(__file__).with_name("static")))
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="prototype")
