import pytest
from fastapi.testclient import TestClient

from sawtai.main import app

pytestmark = pytest.mark.integration


def test_seeded_read_routes() -> None:
    paths = (
        "/api/v1/health/ready",
        "/api/v1/analytics/overview",
        "/api/v1/analytics/timeseries",
        "/api/v1/messages?limit=3",
        "/api/v1/alerts",
        "/api/v1/forecast/replay",
        "/api/v1/search/documents",
        "/api/v1/audit",
        "/api/v1/data/tables",
        "/api/v1/data/tables/messages?limit=3",
    )
    with TestClient(app) as client:
        for path in paths:
            response = client.get(path) if path != "/api/v1/search/documents" else client.post(path)
            assert response.status_code == 200, f"{path}: {response.text}"


def test_draft_stream_has_grounding_and_completion_events() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/drafts",
            json={
                "kind": "reply",
                "case_id": "00000000-0000-0000-0000-000000000a01",
                "lang": "ar",
                "audience": "citizen",
                "instruction": "اكتب رداً رسمياً عن جدول جمع النفايات",
            },
        )
    assert response.status_code == 200
    assert "event: retrieval" in response.text
    assert "event: verification" in response.text
    assert "event: done" in response.text
