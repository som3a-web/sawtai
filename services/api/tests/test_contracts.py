import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sawtai.data.routes import DATASETS
from sawtai.main import app
from sawtai.rag.routes import DraftRequest, event


def test_openapi_contains_prototype_routes() -> None:
    required_paths = {
        "/api/v1/analytics/overview",
        "/api/v1/analytics/timeseries",
        "/api/v1/messages",
        "/api/v1/drafts",
        "/api/v1/alerts",
        "/api/v1/forecast/replay",
        "/api/v1/audit",
        "/api/v1/data/tables",
        "/api/v1/channels/whatsapp/webhook",
        "/api/v1/channels/whatsapp/status",
        "/api/v1/channels/whatsapp/inbox",
        "/api/v1/channels/whatsapp/replies/{response_id}",
        "/api/v1/channels/whatsapp/replies/{response_id}/submit",
        "/api/v1/channels/whatsapp/replies/{response_id}/approve-and-send",
        "/api/v1/auth/token",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/users",
        "/api/v1/roles",
    }
    with TestClient(app) as client:
        paths = set(client.get("/api/openapi.json").json()["paths"])
    assert required_paths <= paths


def test_dataset_allowlist_uses_safe_identifiers() -> None:
    assert len(DATASETS) == len(set(DATASETS))
    assert all(name.replace("_", "").isalnum() and name.islower() for name in DATASETS)
    assert "users" not in DATASETS
    assert "pii_vault" not in DATASETS


def test_sse_event_contract_preserves_arabic() -> None:
    encoded = event("token", {"delta": "مرحباً"})
    event_line, data_line = encoded.strip().splitlines()
    assert event_line == "event: token"
    assert json.loads(data_line.removeprefix("data: ")) == {"delta": "مرحباً"}


def test_draft_request_validates_instruction_length() -> None:
    with pytest.raises(ValidationError):
        DraftRequest(instruction="x")

    request = DraftRequest(instruction="اكتب رداً رسمياً")
    assert request.lang == "ar"
    assert request.kind == "reply"
