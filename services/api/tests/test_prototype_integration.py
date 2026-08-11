from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from sawtai.channels.models import WhatsAppMessage, WhatsAppMetadata
from sawtai.channels.service import approve_and_deliver_reply, process_whatsapp_message
from sawtai.config import get_settings
from sawtai.database import session_factory
from sawtai.main import app
from sawtai.seed import TENANT_ID, USER_ID

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
        "/api/v1/channels/whatsapp/inbox?limit=3",
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


@pytest.mark.asyncio
async def test_whatsapp_message_to_approved_delivery_flow() -> None:
    request_reference = uuid4()
    message = WhatsAppMessage.model_validate(
        {
            "id": f"wamid.integration-{uuid4()}",
            "from": "971501112233",
            "timestamp": "1786464000",
            "type": "text",
            "text": {"body": f"تأخر جمع النفايات ونحتاج متابعة البلاغ {request_reference}"},
        }
    )
    settings = get_settings().model_copy(
        update={
            "whatsapp_delivery_mode": "simulate",
            "whatsapp_reply_mode": "draft",
            "rag_lexical_gate": 0.1,
        }
    )
    async with session_factory() as session:
        result = await process_whatsapp_message(
            session,
            message=message,
            metadata=WhatsAppMetadata(phone_number_id="demo-phone"),
            settings=settings,
        )
    assert result.message_id is not None
    assert result.response_id is not None
    assert result.status == "draft_ready"

    async with session_factory() as session:
        delivery = await approve_and_deliver_reply(
            session,
            response_id=result.response_id,
            tenant_id=TENANT_ID,
            approver_user_id=USER_ID,
            settings=settings,
            comment="integration approval",
        )
    assert delivery.status == "published"
    assert delivery.simulated
    assert delivery.published_ref.startswith("simulated:")
