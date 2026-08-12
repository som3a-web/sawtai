"""Case workflow, deterministic routing, SLA tracking, and history."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.audit.service import write_audit

OPEN_STATUSES = {"new", "triaged", "assigned", "awaiting_response", "responded"}
STATUS_TRANSITIONS = {
    "new": {"triaged", "assigned", "rejected"},
    "triaged": {"assigned", "rejected"},
    "assigned": {"awaiting_response", "responded", "resolved"},
    "awaiting_response": {"assigned", "responded", "resolved"},
    "responded": {"awaiting_response", "resolved"},
    "resolved": {"assigned", "closed"},
    "closed": set(),
    "rejected": set(),
}


def sla_state(status: str, sla_due_at: datetime | None, now: datetime | None = None) -> str:
    if status not in OPEN_STATUSES:
        return "completed"
    if sla_due_at is None:
        return "not_set"
    current = now or datetime.now(UTC)
    if sla_due_at <= current:
        return "breached"
    if sla_due_at <= current + timedelta(hours=4):
        return "due_soon"
    return "on_track"


def enrich_case(row: dict[str, Any]) -> dict[str, Any]:
    due_at = row.get("sla_due_at")
    row["sla_state"] = sla_state(str(row["status"]), due_at)
    if due_at and str(row["status"]) in OPEN_STATUSES:
        row["sla_remaining_seconds"] = int((due_at - datetime.now(UTC)).total_seconds())
    else:
        row["sla_remaining_seconds"] = None
    return row


async def list_cases(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    status_filter: str | None,
    severity_filter: str | None,
    assigned_to: UUID | None,
    search: str | None,
    limit: int,
    case_id: UUID | None = None,
) -> dict[str, object]:
    rows = (
        await session.execute(
            text(
                """
                SELECT c.case_id, c.reference, c.title_ar, c.title_en,
                       c.status::text, c.severity::text, c.sla_due_at,
                       c.first_response_at, c.resolved_at, c.complaint_count,
                       c.created_at, c.updated_at, c.node_id, c.org_unit_id,
                       c.assigned_to, t.code AS taxonomy_code,
                       t.label_ar AS taxonomy_label_ar, t.label_en AS taxonomy_label_en,
                       t.sla_hours, o.name_ar AS org_name_ar, o.name_en AS org_name_en,
                       u.display_name_ar AS assignee_name_ar,
                       u.display_name_en AS assignee_name_en
                FROM core.cases c
                LEFT JOIN core.taxonomy_nodes t ON t.node_id = c.node_id
                LEFT JOIN core.org_units o ON o.org_unit_id = c.org_unit_id
                LEFT JOIN core.users u ON u.user_id = c.assigned_to
                WHERE c.tenant_id = :tenant_id
                  AND (CAST(:case_id AS uuid) IS NULL OR c.case_id = CAST(:case_id AS uuid))
                  AND (CAST(:status_filter AS text) IS NULL OR c.status::text = CAST(:status_filter AS text))
                  AND (CAST(:severity_filter AS text) IS NULL OR c.severity::text = CAST(:severity_filter AS text))
                  AND (CAST(:assigned_to AS uuid) IS NULL OR c.assigned_to = CAST(:assigned_to AS uuid))
                  AND (
                    CAST(:search AS text) IS NULL OR c.reference ILIKE '%' || CAST(:search AS text) || '%'
                    OR c.title_ar ILIKE '%' || CAST(:search AS text) || '%'
                    OR c.title_en ILIKE '%' || CAST(:search AS text) || '%'
                  )
                ORDER BY
                  CASE WHEN c.status IN ('closed','resolved','rejected') THEN 1 ELSE 0 END,
                  c.sla_due_at NULLS LAST, c.updated_at DESC
                LIMIT :limit
                """
            ),
            {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "status_filter": status_filter,
                "severity_filter": severity_filter,
                "assigned_to": assigned_to,
                "search": search.strip() if search else None,
                "limit": limit,
            },
        )
    ).mappings().all()
    items = [enrich_case(dict(row)) for row in rows]
    summary_row = (
        await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE status IN ('new','triaged','assigned','awaiting_response','responded')) AS open,
                       count(*) FILTER (WHERE status IN ('new','triaged','assigned','awaiting_response','responded') AND sla_due_at < now()) AS breached,
                       count(*) FILTER (WHERE status IN ('new','triaged','assigned','awaiting_response','responded') AND assigned_to IS NULL) AS unassigned,
                       count(*) FILTER (WHERE status IN ('new','triaged','assigned','awaiting_response','responded') AND severity = 'critical') AS critical
                FROM core.cases WHERE tenant_id = :tenant_id
                """
            ),
            {"tenant_id": tenant_id},
        )
    ).mappings().one()
    summary = {key: int(summary_row[key]) for key in ("total", "open", "breached", "unassigned", "critical")}
    return {"items": items, "summary": summary}


async def get_case_detail(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    case_id: UUID,
) -> dict[str, object]:
    result = await list_cases(
        session,
        tenant_id=tenant_id,
        status_filter=None,
        severity_filter=None,
        assigned_to=None,
        search=None,
        limit=1,
        case_id=case_id,
    )
    items = result["items"]
    if not isinstance(items, list) or not items:
        raise LookupError("Case not found")
    case = items[0]
    history = (
        await session.execute(
            text(
                """
                SELECT a.audit_id, a.occurred_at, a.action, a.outcome,
                       a.before_state, a.after_state,
                       u.display_name_ar AS actor_name_ar,
                       u.display_name_en AS actor_name_en
                FROM core.audit_log a
                LEFT JOIN core.users u ON u.user_id = a.actor_user_id
                WHERE a.tenant_id = :tenant_id AND a.object_type = 'case'
                  AND a.object_id = :case_id
                ORDER BY a.occurred_at DESC, a.audit_id DESC
                LIMIT 100
                """
            ),
            {"tenant_id": tenant_id, "case_id": case_id},
        )
    ).mappings().all()
    responses = (
        await session.execute(
            text(
                """
                SELECT response_id, kind::text, status::text, body, grounding_score,
                       created_at, approved_at, published_at
                FROM core.responses
                WHERE tenant_id = :tenant_id AND case_id = :case_id
                ORDER BY created_at DESC
                """
            ),
            {"tenant_id": tenant_id, "case_id": case_id},
        )
    ).mappings().all()
    return dict(case) | {
        "history": [dict(row) for row in history],
        "responses": [dict(row) for row in responses],
        "allowed_transitions": sorted(STATUS_TRANSITIONS[str(case["status"])]),
    }


async def create_case(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    title_ar: str,
    title_en: str,
    node_id: UUID | None,
    severity: str,
) -> UUID:
    org_unit_id = None
    sla_hours = None
    if node_id is not None:
        routing = (
            await session.execute(
                text(
                    """
                    SELECT owner_org_unit_id, sla_hours
                    FROM core.taxonomy_nodes
                    WHERE node_id = :node_id AND tenant_id = :tenant_id AND is_active
                    """
                ),
                {"node_id": node_id, "tenant_id": tenant_id},
            )
        ).mappings().one_or_none()
        if routing is None:
            raise ValueError("Taxonomy node is unavailable")
        org_unit_id = routing["owner_org_unit_id"]
        sla_hours = routing["sla_hours"]
    case_id = uuid4()
    reference = f"SHJ-{datetime.now(UTC).year}-{case_id.hex[:6].upper()}"
    sla_due_at = datetime.now(UTC) + timedelta(hours=sla_hours) if sla_hours else None
    await session.execute(
        text(
            """
            INSERT INTO core.cases (
                case_id, tenant_id, reference, title_ar, title_en, node_id,
                org_unit_id, status, severity, sla_due_at
            ) VALUES (
                :case_id, :tenant_id, :reference, :title_ar, :title_en,
                :node_id, :org_unit_id, 'new', CAST(:severity AS core.complaint_severity),
                :sla_due_at
            )
            """
        ),
        {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "reference": reference,
            "title_ar": title_ar.strip(),
            "title_en": title_en.strip(),
            "node_id": node_id,
            "org_unit_id": org_unit_id,
            "severity": severity,
            "sla_due_at": sla_due_at,
        },
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(actor_user_id),
        action="case.create",
        object_type="case",
        object_id=str(case_id),
        after_state={"reference": reference, "status": "new", "severity": severity},
    )
    await session.commit()
    return case_id


async def update_case(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    case_id: UUID,
    title_ar: str | None,
    title_en: str | None,
    severity: str | None,
) -> None:
    row = (
        await session.execute(
            text(
                "SELECT title_ar, title_en, severity::text FROM core.cases "
                "WHERE case_id = :case_id AND tenant_id = :tenant_id FOR UPDATE"
            ),
            {"case_id": case_id, "tenant_id": tenant_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Case not found")
    values = {
        "title_ar": title_ar.strip() if title_ar is not None else row["title_ar"],
        "title_en": title_en.strip() if title_en is not None else row["title_en"],
        "severity": severity or row["severity"],
    }
    await session.execute(
        text(
            """
            UPDATE core.cases SET title_ar = :title_ar, title_en = :title_en,
                severity = CAST(:severity AS core.complaint_severity), updated_at = now()
            WHERE case_id = :case_id AND tenant_id = :tenant_id
            """
        ),
        values | {"case_id": case_id, "tenant_id": tenant_id},
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id), actor_user_id=str(actor_user_id), action="case.update",
        object_type="case", object_id=str(case_id), before_state=dict(row), after_state=values,
    )
    await session.commit()


async def assign_case(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    case_id: UUID,
    assignee_user_id: UUID,
) -> None:
    target = (
        await session.execute(
            text(
                "SELECT user_id FROM core.users WHERE user_id = :user_id "
                "AND tenant_id = :tenant_id AND is_active"
            ),
            {"user_id": assignee_user_id, "tenant_id": tenant_id},
        )
    ).scalar_one_or_none()
    if target is None:
        raise ValueError("Assignee is unavailable")
    row = (
        await session.execute(
            text(
                "SELECT assigned_to, status::text FROM core.cases "
                "WHERE case_id = :case_id AND tenant_id = :tenant_id FOR UPDATE"
            ),
            {"case_id": case_id, "tenant_id": tenant_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Case not found")
    status = "assigned" if row["status"] in {"new", "triaged", "resolved"} else row["status"]
    await session.execute(
        text(
            """
            UPDATE core.cases SET assigned_to = :assignee, status = CAST(:status AS core.case_status),
                resolved_at = CASE WHEN :status = 'assigned' THEN NULL ELSE resolved_at END,
                updated_at = now()
            WHERE case_id = :case_id AND tenant_id = :tenant_id
            """
        ),
        {"assignee": assignee_user_id, "status": status, "case_id": case_id, "tenant_id": tenant_id},
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id), actor_user_id=str(actor_user_id), action="case.assign",
        object_type="case", object_id=str(case_id),
        before_state={"assigned_to": str(row["assigned_to"]) if row["assigned_to"] else None, "status": row["status"]},
        after_state={"assigned_to": str(assignee_user_id), "status": status},
    )
    await session.commit()


async def transition_case(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    case_id: UUID,
    next_status: str,
    note: str | None,
) -> None:
    current = (
        await session.execute(
            text(
                "SELECT status::text, assigned_to FROM core.cases "
                "WHERE case_id = :case_id AND tenant_id = :tenant_id FOR UPDATE"
            ),
            {"case_id": case_id, "tenant_id": tenant_id},
        )
    ).mappings().one_or_none()
    if current is None:
        raise LookupError("Case not found")
    if next_status not in STATUS_TRANSITIONS[str(current["status"])]:
        raise ValueError(f"Case cannot move from {current['status']} to {next_status}")
    if next_status in {"assigned", "awaiting_response", "responded", "resolved"} and current["assigned_to"] is None:
        raise ValueError("Assign the case before changing to this status")
    await session.execute(
        text(
            """
            UPDATE core.cases SET status = CAST(:status AS core.case_status),
                first_response_at = CASE WHEN :status = 'responded' THEN COALESCE(first_response_at, now()) ELSE first_response_at END,
                resolved_at = CASE WHEN :status IN ('resolved','closed') THEN COALESCE(resolved_at, now()) WHEN :status = 'assigned' THEN NULL ELSE resolved_at END,
                updated_at = now()
            WHERE case_id = :case_id AND tenant_id = :tenant_id
            """
        ),
        {"status": next_status, "case_id": case_id, "tenant_id": tenant_id},
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id), actor_user_id=str(actor_user_id), action="case.status",
        object_type="case", object_id=str(case_id), before_state={"status": current["status"]},
        after_state={"status": next_status, "note": note},
    )
    await session.commit()


async def add_case_note(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    case_id: UUID,
    note: str,
) -> None:
    exists = (
        await session.execute(
            text("SELECT 1 FROM core.cases WHERE case_id = :case_id AND tenant_id = :tenant_id"),
            {"case_id": case_id, "tenant_id": tenant_id},
        )
    ).scalar_one_or_none()
    if exists is None:
        raise LookupError("Case not found")
    await write_audit(
        session,
        tenant_id=str(tenant_id), actor_user_id=str(actor_user_id), action="case.note",
        object_type="case", object_id=str(case_id), after_state={"note": note.strip()},
    )
    await session.execute(
        text("UPDATE core.cases SET updated_at = now() WHERE case_id = :case_id"),
        {"case_id": case_id},
    )
    await session.commit()


async def escalate_case(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    case_id: UUID,
    reason: str,
) -> None:
    current = (
        await session.execute(
            text(
                "UPDATE core.cases SET severity = 'critical', updated_at = now() "
                "WHERE case_id = :case_id AND tenant_id = :tenant_id "
                "RETURNING severity::text"
            ),
            {"case_id": case_id, "tenant_id": tenant_id},
        )
    ).scalar_one_or_none()
    if current is None:
        raise LookupError("Case not found")
    await write_audit(
        session,
        tenant_id=str(tenant_id), actor_user_id=str(actor_user_id), action="case.escalate",
        object_type="case", object_id=str(case_id),
        after_state={"severity": "critical", "reason": reason.strip()},
    )
    await session.commit()


async def create_case_from_message(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    message_id: UUID,
    occurred_at: datetime,
    raw_text: str,
) -> UUID:
    existing = (
        await session.execute(
            text(
                "SELECT case_id FROM core.complaints WHERE tenant_id = :tenant_id "
                "AND message_id = :message_id AND occurred_at = :occurred_at LIMIT 1"
            ),
            {"tenant_id": tenant_id, "message_id": message_id, "occurred_at": occurred_at},
        )
    ).scalar_one_or_none()
    if existing is not None:
        return UUID(str(existing))

    lowered = raw_text.lower()
    category = (
        "waste" if any(word in lowered for word in ("نفايات", "حاويات", "waste", "garbage"))
        else "roads" if any(word in lowered for word in ("طريق", "حفرة", "إنارة", "road", "pothole"))
        else "parks" if any(word in lowered for word in ("حديقة", "ألعاب", "park", "playground"))
        else "permits" if any(word in lowered for word in ("تصريح", "معاملة", "permit", "application"))
        else None
    )
    routing = (
        await session.execute(
            text(
                """
                SELECT node_id, owner_org_unit_id, sla_hours, label_ar, label_en
                FROM core.taxonomy_nodes
                WHERE tenant_id = :tenant_id AND is_active
                ORDER BY CASE WHEN CAST(:category AS text) IS NOT NULL
                    AND code LIKE CAST(:category AS text) || '%' THEN 0 ELSE 1 END, code
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "category": category},
        )
    ).mappings().one_or_none()
    urgent = any(word in lowered for word in ("عاجل", "خطر", "حادث", "urgent", "danger", "emergency"))
    severity = "high" if urgent else "medium"
    case_id = uuid4()
    reference = f"SHJ-{datetime.now(UTC).year}-{case_id.hex[:6].upper()}"
    sla_due_at = datetime.now(UTC) + timedelta(hours=routing["sla_hours"]) if routing and routing["sla_hours"] else None
    title_ar = raw_text.strip()[:180]
    title_en = routing["label_en"] if routing else "WhatsApp service request"
    await session.execute(
        text(
            """
            INSERT INTO core.cases (
                case_id, tenant_id, reference, title_ar, title_en, node_id,
                org_unit_id, status, severity, sla_due_at
            ) VALUES (
                :case_id, :tenant_id, :reference, :title_ar, :title_en,
                :node_id, :org_unit_id, 'new', CAST(:severity AS core.complaint_severity),
                :sla_due_at
            )
            """
        ),
        {
            "case_id": case_id, "tenant_id": tenant_id, "reference": reference,
            "title_ar": title_ar, "title_en": title_en,
            "node_id": routing["node_id"] if routing else None,
            "org_unit_id": routing["owner_org_unit_id"] if routing else None,
            "severity": severity, "sla_due_at": sla_due_at,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO core.complaints (
                tenant_id, message_id, occurred_at, node_id, severity,
                issue_summary_ar, issue_summary_en, case_id
            ) VALUES (
                :tenant_id, :message_id, :occurred_at, :node_id,
                CAST(:severity AS core.complaint_severity), :summary_ar, :summary_en, :case_id
            )
            """
        ),
        {
            "tenant_id": tenant_id, "message_id": message_id, "occurred_at": occurred_at,
            "node_id": routing["node_id"] if routing else None, "severity": severity,
            "summary_ar": title_ar, "summary_en": title_en, "case_id": case_id,
        },
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id), actor_user_id=None, actor_type="worker",
        action="case.create_from_message", object_type="case", object_id=str(case_id),
        after_state={"reference": reference, "message_id": str(message_id), "severity": severity},
    )
    return case_id
