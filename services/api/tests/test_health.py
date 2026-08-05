from fastapi.testclient import TestClient

from sawtai.config import postgres_url_with_driver
from sawtai.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_render_database_url_is_adapted_for_sqlalchemy() -> None:
    render_url = "postgresql://sawtai:secret@database.render-internal.com/sawtai"

    assert postgres_url_with_driver(render_url, "asyncpg") == (
        "postgresql+asyncpg://sawtai:secret@database.render-internal.com/sawtai"
    )
    assert postgres_url_with_driver(render_url, "psycopg") == (
        "postgresql+psycopg://sawtai:secret@database.render-internal.com/sawtai"
    )


def test_non_postgres_url_is_not_changed() -> None:
    assert postgres_url_with_driver("sqlite+aiosqlite:///test.db", "asyncpg") == (
        "sqlite+aiosqlite:///test.db"
    )
