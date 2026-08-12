from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from sawtai.channels.models import WhatsAppMessage, WhatsAppMetadata
from sawtai.channels.service import (
    approve_and_deliver_reply,
    process_whatsapp_message,
    submit_whatsapp_reply,
    update_whatsapp_reply,
)
from sawtai.config import get_settings
from sawtai.database import session_factory
from sawtai.main import app
from sawtai.seed import APPROVER_USER_ID, TENANT_ID, USER_ID

pytestmark = pytest.mark.integration


def test_auth_sessions_and_least_privilege_roles() -> None:
    with TestClient(app) as client:
        officer = client.post(
            "/api/v1/auth/token",
            json={"email": "officer@sawtai.ae", "password": "SawtAI-2026!"},
        )
        assert officer.status_code == 200
        officer_headers = {"Authorization": f"Bearer {officer.json()['access_token']}"}
        assert client.get("/api/v1/auth/me", headers=officer_headers).status_code == 200
        assert client.get("/api/v1/users", headers=officer_headers).status_code == 403

        administrator = client.post(
            "/api/v1/auth/token",
            json={"email": "admin@sawtai.ae", "password": "SawtAI-2026!"},
        )
        assert administrator.status_code == 200
        admin_headers = {"Authorization": f"Bearer {administrator.json()['access_token']}"}
        assert client.get("/api/v1/users", headers=admin_headers).status_code == 200
        assert client.get("/api/v1/channels/whatsapp/inbox", headers=admin_headers).status_code == 403
        assert client.get("/api/v1/cases", headers=admin_headers).status_code == 403
        assert client.post("/api/v1/auth/refresh").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.post("/api/v1/auth/refresh").status_code == 401


def test_seeded_read_routes() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/health/ready").status_code == 200
        role_paths = {
            "officer@sawtai.ae": (
                "/api/v1/analytics/overview",
                "/api/v1/analytics/timeseries",
                "/api/v1/messages?limit=3",
                "/api/v1/search/documents",
                "/api/v1/channels/whatsapp/inbox?limit=3",
                "/api/v1/cases?limit=3",
            ),
            "crisis@sawtai.ae": ("/api/v1/alerts", "/api/v1/forecast/replay"),
            "dpo@sawtai.ae": (
                "/api/v1/audit",
                "/api/v1/data/tables",
                "/api/v1/data/tables/messages?limit=3",
            ),
        }
        for email, paths in role_paths.items():
            login = client.post("/api/v1/auth/token", json={"email": email, "password": "SawtAI-2026!"})
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            for path in paths:
                response = client.post(path, headers=headers) if path == "/api/v1/search/documents" else client.get(path, headers=headers)
                assert response.status_code == 200, f"{path}: {response.text}"


def test_case_creation_routing_assignment_and_lifecycle() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/token",
            json={"email": "officer@sawtai.ae", "password": "SawtAI-2026!"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        metadata = client.get("/api/v1/cases/metadata", headers=headers)
        assert metadata.status_code == 200
        taxonomy = metadata.json()["taxonomy"][0]
        assignee = metadata.json()["assignees"][0]

        created = client.post(
            "/api/v1/cases",
            headers=headers,
            json={
                "title_ar": "اختبار دورة حياة الحالة",
                "title_en": "Case lifecycle integration test",
                "node_id": taxonomy["node_id"],
                "severity": "medium",
            },
        )
        assert created.status_code == 201, created.text
        case_id = created.json()["case_id"]
        detail = client.get(f"/api/v1/cases/{case_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["status"] == "new"
        assert detail.json()["sla_due_at"] is not None
        assert detail.json()["org_unit_id"] is not None

        triaged = client.post(
            f"/api/v1/cases/{case_id}/status",
            headers=headers,
            json={"status": "triaged", "note": "Validated by integration test"},
        )
        assert triaged.status_code == 200
        assigned = client.post(
            f"/api/v1/cases/{case_id}/assign",
            headers=headers,
            json={"assigned_to": assignee["user_id"]},
        )
        assert assigned.status_code == 200
        noted = client.post(
            f"/api/v1/cases/{case_id}/notes",
            headers=headers,
            json={"note": "Internal follow-up recorded"},
        )
        assert noted.status_code == 200
        escalated = client.post(
            f"/api/v1/cases/{case_id}/escalate",
            headers=headers,
            json={"reason": "Urgent service impact"},
        )
        assert escalated.status_code == 200

        for next_status in ("awaiting_response", "responded", "resolved", "closed"):
            changed = client.post(
                f"/api/v1/cases/{case_id}/status",
                headers=headers,
                json={"status": next_status},
            )
            assert changed.status_code == 200, changed.text

        final = client.get(f"/api/v1/cases/{case_id}", headers=headers).json()
        assert final["status"] == "closed"
        assert final["severity"] == "critical"
        assert final["first_response_at"] is not None
        assert final["resolved_at"] is not None
        actions = {event["action"] for event in final["history"]}
        assert {"case.create", "case.assign", "case.note", "case.escalate", "case.status"} <= actions


def test_draft_stream_has_grounding_and_completion_events() -> None:
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/token", json={"email": "officer@sawtai.ae", "password": "SawtAI-2026!"})
        response = client.post(
            "/api/v1/drafts",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
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
        linked_case = (
            await session.execute(
                text(
                    """
                    SELECT r.case_id
                    FROM core.responses r
                    JOIN core.complaints c ON c.case_id = r.case_id
                    WHERE r.response_id = :response_id AND c.message_id = :message_id
                    """
                ),
                {"response_id": result.response_id, "message_id": result.message_id},
            )
        ).scalar_one_or_none()
    assert linked_case is not None

    async with session_factory() as session:
        updated = await update_whatsapp_reply(
            session,
            response_id=result.response_id,
            tenant_id=TENANT_ID,
            editor_user_id=USER_ID,
            body="نشكركم على تواصلكم. يرجى تزويدنا برقم مرجع البلاغ لمتابعة الحالة مع الفريق المختص.",
        )
    assert updated.status == "draft"
    assert updated.edit_distance > 0

    async with session_factory() as session:
        submitted = await submit_whatsapp_reply(
            session,
            response_id=result.response_id,
            tenant_id=TENANT_ID,
            submitter_user_id=USER_ID,
        )
    assert submitted.status == "pending_approval"

    async with session_factory() as session:
        delivery = await approve_and_deliver_reply(
            session,
            response_id=result.response_id,
            tenant_id=TENANT_ID,
            approver_user_id=APPROVER_USER_ID,
            settings=settings,
            comment="integration approval",
        )
    assert delivery.status == "published"
    assert delivery.simulated
    assert delivery.published_ref.startswith("simulated:")
