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
                response = (
                    client.post(path, headers=headers, json={"query": "جمع النفايات"})
                    if path == "/api/v1/search/documents"
                    else client.get(path, headers=headers)
                )
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


def test_notification_deduplication_and_read_state() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/token",
            json={"email": "officer@sawtai.ae", "password": "SawtAI-2026!"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        current_user = client.get("/api/v1/auth/me", headers=headers).json()
        metadata = client.get("/api/v1/cases/metadata", headers=headers).json()
        taxonomy = metadata["taxonomy"][0]
        created = client.post(
            "/api/v1/cases",
            headers=headers,
            json={
                "title_ar": "اختبار إشعارات الحالة",
                "title_en": "Notification workflow integration test",
                "node_id": taxonomy["node_id"],
                "severity": "medium",
            },
        )
        assert created.status_code == 201, created.text
        case_id = created.json()["case_id"]
        assigned = client.post(
            f"/api/v1/cases/{case_id}/assign",
            headers=headers,
            json={"assigned_to": current_user["user_id"]},
        )
        assert assigned.status_code == 200, assigned.text

        first = client.get("/api/v1/notifications?limit=200", headers=headers)
        assert first.status_code == 200, first.text
        matching = [item for item in first.json()["items"] if item["target_id"] == case_id]
        assert len(matching) == 1
        assert matching[0]["kind"] == "case_assigned"
        assert matching[0]["is_read"] is False

        second = client.get("/api/v1/notifications?limit=200", headers=headers)
        assert second.status_code == 200
        assert second.json()["count"] == first.json()["count"]
        assert len([item for item in second.json()["items"] if item["target_id"] == case_id]) == 1

        notification_id = matching[0]["notification_id"]
        marked = client.post(f"/api/v1/notifications/{notification_id}/read", headers=headers)
        assert marked.status_code == 200
        refreshed = client.get("/api/v1/notifications?limit=200", headers=headers).json()
        refreshed_item = next(item for item in refreshed["items"] if item["notification_id"] == notification_id)
        assert refreshed_item["is_read"] is True

        marked_all = client.post("/api/v1/notifications/read-all", headers=headers)
        assert marked_all.status_code == 200
        assert client.get("/api/v1/notifications?limit=200", headers=headers).json()["unread"] == 0


def test_notification_read_is_scoped_to_recipient() -> None:
    with TestClient(app) as client:
        officer_login = client.post(
            "/api/v1/auth/token",
            json={"email": "officer@sawtai.ae", "password": "SawtAI-2026!"},
        )
        officer_headers = {"Authorization": f"Bearer {officer_login.json()['access_token']}"}
        notifications = client.get("/api/v1/notifications", headers=officer_headers).json()["items"]
        assert notifications

        crisis_login = client.post(
            "/api/v1/auth/token",
            json={"email": "crisis@sawtai.ae", "password": "SawtAI-2026!"},
        )
        crisis_headers = {"Authorization": f"Bearer {crisis_login.json()['access_token']}"}
        denied = client.post(
            f"/api/v1/notifications/{notifications[0]['notification_id']}/read",
            headers=crisis_headers,
        )
        assert denied.status_code == 404


def test_governed_knowledge_source_lifecycle() -> None:
    unique_phrase = f"سياسة التكامل المرجعية {uuid4()}"
    with TestClient(app) as client:
        officer_login = client.post(
            "/api/v1/auth/token",
            json={"email": "officer@sawtai.ae", "password": "SawtAI-2026!"},
        )
        officer_headers = {"Authorization": f"Bearer {officer_login.json()['access_token']}"}
        library = client.get("/api/v1/documents", headers=officer_headers)
        assert library.status_code == 200, library.text
        assert library.json()["summary"]["total"] >= 1
        created = client.post(
            "/api/v1/documents",
            headers=officer_headers,
            json={
                "kind": "service_guide",
                "title_ar": "دليل اختبار حوكمة المعرفة",
                "title_en": "Knowledge governance integration guide",
                "lang": "ar",
                "version": str(uuid4()),
                "heading_path": "الخدمات > اختبار التكامل",
                "content": f"# إجراء الخدمة\n\n{unique_phrase}. يتم تنفيذ الإجراء خلال يوم عمل واحد وفق الدليل المعتمد.",
            },
        )
        assert created.status_code == 201, created.text
        document_id = created.json()["document_id"]

        pending_search = client.post(
            "/api/v1/search/documents",
            headers=officer_headers,
            json={"query": unique_phrase},
        )
        assert pending_search.status_code == 200
        assert all(result["document"]["document_id"] != document_id for result in pending_search.json()["results"])
        assert client.post(f"/api/v1/documents/{document_id}/approve", headers=officer_headers).status_code == 403
        reindexed = client.post(f"/api/v1/documents/{document_id}/reindex", headers=officer_headers)
        assert reindexed.status_code == 200
        assert reindexed.json()["chunks"] >= 1

        approver_login = client.post(
            "/api/v1/auth/token",
            json={"email": "approver@sawtai.ae", "password": "SawtAI-2026!"},
        )
        approver_headers = {"Authorization": f"Bearer {approver_login.json()['access_token']}"}
        approved = client.post(f"/api/v1/documents/{document_id}/approve", headers=approver_headers)
        assert approved.status_code == 200, approved.text
        detail = client.get(f"/api/v1/documents/{document_id}", headers=approver_headers)
        assert detail.status_code == 200
        assert detail.json()["is_approved"] is True
        assert detail.json()["created_by"] == str(USER_ID)
        assert detail.json()["approved_by"] == str(APPROVER_USER_ID)
        assert {event["action"] for event in detail.json()["history"]} >= {
            "document.create",
            "document.reindex",
            "document.approve",
        }

        approved_search = client.post(
            "/api/v1/search/documents",
            headers=officer_headers,
            json={"query": unique_phrase},
        )
        assert approved_search.status_code == 200
        assert any(result["document"]["document_id"] == document_id for result in approved_search.json()["results"])
        grounded_draft = client.post(
            "/api/v1/drafts",
            headers=officer_headers,
            json={
                "kind": "reply",
                "lang": "ar",
                "audience": "citizen",
                "instruction": unique_phrase,
            },
        )
        assert grounded_draft.status_code == 200
        assert "event: done" in grounded_draft.text
        assert "دليل اختبار حوكمة المعرفة" in grounded_draft.text
        cited_reindex = client.post(f"/api/v1/documents/{document_id}/reindex", headers=officer_headers)
        assert cited_reindex.status_code == 200

        retired = client.delete(f"/api/v1/documents/{document_id}", headers=approver_headers)
        assert retired.status_code == 200
        retired_detail = client.get(f"/api/v1/documents/{document_id}", headers=approver_headers).json()
        assert retired_detail["is_approved"] is False
        assert retired_detail["effective_to"] is not None
        retired_search = client.post(
            "/api/v1/search/documents",
            headers=officer_headers,
            json={"query": unique_phrase},
        )
        assert all(result["document"]["document_id"] != document_id for result in retired_search.json()["results"])


def test_document_creator_cannot_self_approve() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/token",
            json={"email": "approver@sawtai.ae", "password": "SawtAI-2026!"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        created = client.post(
            "/api/v1/documents",
            headers=headers,
            json={
                "kind": "faq",
                "title_ar": "اختبار منع الاعتماد الذاتي",
                "lang": "ar",
                "version": str(uuid4()),
                "content": "هذا محتوى اختباري موثوق للتأكد من منع منشئ المستند من اعتماد المصدر بنفسه.",
            },
        )
        assert created.status_code == 201
        denied = client.post(
            f"/api/v1/documents/{created.json()['document_id']}/approve",
            headers=headers,
        )
        assert denied.status_code == 403


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
    assert "دليل بلاغات جمع النفايات" in response.text


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
