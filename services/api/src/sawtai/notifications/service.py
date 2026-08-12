"""Durable notification outbox backed by the append-only audit ledger."""

from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.audit.service import write_audit


class NotificationTarget(TypedDict):
    session: AsyncSession
    tenant_id: UUID
    target_type: str
    target_id: UUID
    target_page: str
    reference: str | None


def notification_id(kind: str, target_id: UUID, recipient_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"https://sawtai.ae/notification/{kind}/{target_id}/{recipient_id}")


async def _emit(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    recipient_id: UUID,
    kind: str,
    level: str,
    title_ar: str,
    title_en: str,
    body_ar: str,
    body_en: str,
    target_type: str,
    target_id: UUID,
    target_page: str,
    reference: str | None,
) -> None:
    event_id = notification_id(kind, target_id, recipient_id)
    exists = (
        await session.execute(
            text(
                """
                SELECT 1 FROM core.audit_log
                WHERE tenant_id = :tenant_id AND object_type = 'notification'
                  AND object_id = :event_id AND action = 'notification.trigger'
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": event_id},
        )
    ).scalar_one_or_none()
    if exists is not None:
        return
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=None,
        actor_type="system",
        action="notification.trigger",
        object_type="notification",
        object_id=str(event_id),
        after_state={
            "recipient_user_id": str(recipient_id),
            "kind": kind,
            "level": level,
            "title_ar": title_ar,
            "title_en": title_en,
            "body_ar": body_ar,
            "body_en": body_en,
            "target_type": target_type,
            "target_id": str(target_id),
            "target_page": target_page,
            "reference": reference,
        },
    )


async def evaluate_notification_rules(
    session: AsyncSession,
    *,
    tenant_id: UUID | None = None,
) -> int:
    tenants = (
        [tenant_id]
        if tenant_id is not None
        else list((await session.execute(text("SELECT tenant_id FROM core.tenants"))).scalars().all())
    )
    before_count = 0
    for current_tenant in tenants:
        before_count += await _evaluate_tenant(session, UUID(str(current_tenant)))
    return before_count


async def _evaluate_tenant(session: AsyncSession, tenant_id: UUID) -> int:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:tenant_key, 0))"),
        {"tenant_key": str(tenant_id)},
    )
    existing_count = (
        await session.execute(
            text(
                "SELECT count(*) FROM core.audit_log WHERE tenant_id = :tenant_id "
                "AND action = 'notification.trigger'"
            ),
            {"tenant_id": tenant_id},
        )
    ).scalar_one()
    role_rows = (
        await session.execute(
            text(
                """
                SELECT u.user_id, array_agg(DISTINCT r.code) AS roles
                FROM core.users u
                JOIN core.user_roles ur ON ur.user_id = u.user_id
                JOIN core.roles r ON r.role_id = ur.role_id
                WHERE u.tenant_id = :tenant_id AND u.is_active
                GROUP BY u.user_id
                """
            ),
            {"tenant_id": tenant_id},
        )
    ).mappings().all()
    role_users = {str(row["user_id"]): set(row["roles"]) for row in role_rows}
    case_managers = [UUID(user_id) for user_id, roles in role_users.items() if roles & {"comms_officer", "dept_head"}]
    crisis_leads = [UUID(user_id) for user_id, roles in role_users.items() if "crisis_lead" in roles]
    approvers = [UUID(user_id) for user_id, roles in role_users.items() if "dept_head" in roles]
    now = datetime.now(UTC)
    cases = (
        await session.execute(
            text(
                """
                SELECT case_id, reference, title_ar, title_en, status::text,
                       severity::text, sla_due_at, assigned_to, updated_at
                FROM core.cases
                WHERE tenant_id = :tenant_id
                  AND status IN ('new','triaged','assigned','awaiting_response','responded')
                """
            ),
            {"tenant_id": tenant_id},
        )
    ).mappings().all()
    for case in cases:
        case_id = UUID(str(case["case_id"]))
        assigned_to = UUID(str(case["assigned_to"])) if case["assigned_to"] else None
        common: NotificationTarget = {
            "session": session,
            "tenant_id": tenant_id,
            "target_type": "case",
            "target_id": case_id,
            "target_page": "cases",
            "reference": str(case["reference"]),
        }
        if assigned_to:
            await _emit(
                **common,
                recipient_id=assigned_to,
                kind="case_assigned",
                level="info",
                title_ar="حالة مسندة إليك",
                title_en="Case assigned to you",
                body_ar=str(case["title_ar"]),
                body_en=str(case["title_en"]),
            )
        elif case["status"] in {"new", "triaged"}:
            for recipient in case_managers:
                await _emit(
                    **common,
                    recipient_id=recipient,
                    kind="case_unassigned",
                    level="action",
                    title_ar="حالة جديدة تحتاج مسؤولاً",
                    title_en="New case needs an owner",
                    body_ar=f"{case['reference']} بانتظار الإسناد",
                    body_en=f"{case['reference']} is waiting for assignment",
                )
        if case["sla_due_at"] is not None:
            sla_recipients = [assigned_to] if assigned_to else case_managers
            if case["sla_due_at"] <= now:
                for recipient in sla_recipients:
                    if recipient:
                        await _emit(
                            **common,
                            recipient_id=recipient,
                            kind="sla_breached",
                            level="critical",
                            title_ar="تجاوز اتفاقية مستوى الخدمة",
                            title_en="SLA breached",
                            body_ar=f"تجاوزت الحالة {case['reference']} الموعد المحدد",
                            body_en=f"Case {case['reference']} passed its SLA deadline",
                        )
            elif case["sla_due_at"] <= now + timedelta(hours=4):
                for recipient in sla_recipients:
                    if recipient:
                        await _emit(
                            **common,
                            recipient_id=recipient,
                            kind="sla_due_soon",
                            level="warning",
                            title_ar="موعد SLA يقترب",
                            title_en="SLA deadline approaching",
                            body_ar=f"أقل من أربع ساعات متبقية للحالة {case['reference']}",
                            body_en=f"Less than four hours remain for {case['reference']}",
                        )
        if case["severity"] == "critical":
            critical_recipients = set(crisis_leads)
            if assigned_to:
                critical_recipients.add(assigned_to)
            for recipient in critical_recipients:
                await _emit(
                    **common,
                    recipient_id=recipient,
                    kind="case_critical",
                    level="critical",
                    title_ar="حالة حرجة تتطلب الانتباه",
                    title_en="Critical case requires attention",
                    body_ar=str(case["title_ar"]),
                    body_en=str(case["title_en"]),
                )
        if case["status"] == "awaiting_response" and case["updated_at"] <= now - timedelta(hours=2):
            waiting_recipients = [assigned_to] if assigned_to else case_managers
            for recipient in waiting_recipients:
                if recipient:
                    await _emit(
                        **common,
                        recipient_id=recipient,
                        kind="customer_waiting",
                        level="warning",
                        title_ar="المتعامل ينتظر الرد",
                        title_en="Citizen is waiting",
                        body_ar=f"الحالة {case['reference']} دون تحديث منذ أكثر من ساعتين",
                        body_en=f"Case {case['reference']} has had no update for over two hours",
                    )
    pending = (
        await session.execute(
            text(
                """
                SELECT response_id, created_by, edited_by, submitted_at,
                       left(body, 180) AS body
                FROM core.responses
                WHERE tenant_id = :tenant_id AND status = 'pending_approval'
                """
            ),
            {"tenant_id": tenant_id},
        )
    ).mappings().all()
    for response in pending:
        for recipient in approvers:
            if recipient in {response["created_by"], response["edited_by"]}:
                continue
            await _emit(
                session=session,
                tenant_id=tenant_id,
                recipient_id=recipient,
                kind="draft_approval",
                level="action",
                title_ar="مسودة تنتظر اعتمادك",
                title_en="Draft awaiting your approval",
                body_ar=str(response["body"]),
                body_en="A citizen reply is ready for independent approval",
                target_type="response",
                target_id=UUID(str(response["response_id"])),
                target_page="whatsapp",
                reference=None,
            )
    after_count = (
        await session.execute(
            text(
                "SELECT count(*) FROM core.audit_log WHERE tenant_id = :tenant_id "
                "AND action = 'notification.trigger'"
            ),
            {"tenant_id": tenant_id},
        )
    ).scalar_one()
    return int(after_count) - int(existing_count)


async def list_notifications(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    limit: int,
) -> dict[str, object]:
    await evaluate_notification_rules(session, tenant_id=tenant_id)
    await session.commit()
    rows = (
        await session.execute(
            text(
                """
                SELECT n.object_id AS notification_id, n.occurred_at,
                       n.after_state,
                       EXISTS (
                         SELECT 1 FROM core.audit_log r
                         WHERE r.tenant_id = n.tenant_id
                           AND r.object_type = 'notification'
                           AND r.object_id = n.object_id
                           AND r.action = 'notification.read'
                           AND r.actor_user_id = :user_id
                       ) AS is_read
                FROM core.audit_log n
                WHERE n.tenant_id = :tenant_id
                  AND n.action = 'notification.trigger'
                  AND n.after_state ->> 'recipient_user_id' = :user_id_text
                ORDER BY n.occurred_at DESC, n.audit_id DESC
                LIMIT :limit
                """
            ),
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "user_id_text": str(user_id),
                "limit": limit,
            },
        )
    ).mappings().all()
    items = [
        {
            "notification_id": str(row["notification_id"]),
            "occurred_at": row["occurred_at"],
            "is_read": row["is_read"],
            **dict(row["after_state"]),
        }
        for row in rows
    ]
    return {"items": items, "unread": sum(not item["is_read"] for item in items), "count": len(items)}


async def mark_notification_read(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    event_id: UUID,
) -> None:
    notification = (
        await session.execute(
            text(
                """
                SELECT 1 FROM core.audit_log
                WHERE tenant_id = :tenant_id AND object_id = :event_id
                  AND action = 'notification.trigger'
                  AND after_state ->> 'recipient_user_id' = :user_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": event_id, "user_id": str(user_id)},
        )
    ).scalar_one_or_none()
    if notification is None:
        raise LookupError("Notification not found")
    already_read = (
        await session.execute(
            text(
                """
                SELECT 1 FROM core.audit_log
                WHERE tenant_id = :tenant_id AND object_id = :event_id
                  AND action = 'notification.read' AND actor_user_id = :user_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "event_id": event_id, "user_id": user_id},
        )
    ).scalar_one_or_none()
    if already_read is None:
        await write_audit(
            session,
            tenant_id=str(tenant_id), actor_user_id=str(user_id),
            action="notification.read", object_type="notification", object_id=str(event_id),
            after_state={"read_at": datetime.now(UTC).isoformat()},
        )
        await session.commit()


async def mark_all_notifications_read(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> int:
    result = await list_notifications(session, tenant_id=tenant_id, user_id=user_id, limit=200)
    items = cast(list[dict[str, object]], result["items"])
    unread = [item for item in items if item.get("is_read") is not True]
    for item in unread:
        await mark_notification_read(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            event_id=UUID(str(item["notification_id"])),
        )
    return len(unread)
