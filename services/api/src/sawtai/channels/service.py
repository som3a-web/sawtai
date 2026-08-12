"""Public channel-orchestration facade."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.audit.service import write_audit
from sawtai.cases.service import create_case_from_message
from sawtai.channels.models import WhatsAppMessage, WhatsAppMetadata, WhatsAppStatus
from sawtai.channels.whatsapp import WhatsAppClient, WhatsAppDeliveryError
from sawtai.config import Settings
from sawtai.ingest.service import (
    InboundMessage,
    PersistedMessage,
    persist_inbound_message,
)
from sawtai.rag.service import generate_grounded_reply

ACKNOWLEDGEMENT_AR = (
    "شكراً لتواصلكم معنا. تم استلام رسالتكم وسيتم التعامل معها وفق إجراءات الخدمة المعتمدة."
)
ACKNOWLEDGEMENT_EN = (
    "Thank you for contacting us. Your message has been received and will be handled "
    "according to the approved service process."
)


@dataclass(frozen=True)
class MessageProcessingResult:
    message_id: UUID | None
    response_id: UUID | None
    status: str
    acknowledgement_id: str | None = None


@dataclass(frozen=True)
class ApprovedDelivery:
    response_id: UUID
    status: str
    published_ref: str
    simulated: bool


@dataclass(frozen=True)
class UpdatedReply:
    response_id: UUID
    body: str
    status: str
    edit_distance: int


@dataclass(frozen=True)
class SubmittedReply:
    response_id: UUID
    status: str


async def list_whatsapp_inbox(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    limit: int,
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT m.message_id, m.external_id, m.occurred_at, m.raw_text,
                       m.author_pseudonym,
                       m.lang_primary::text, m.enrichment_state,
                       reply.response_id, reply.body AS reply_body,
                       reply.status::text AS reply_status,
                       reply.grounding_score, reply.abstained,
                       reply.abstain_reason, reply.policy_flags,
                       reply.published_ref, reply.created_at AS reply_created_at,
                       reply.created_by, reply.edited_by, reply.submitted_at,
                       complaint.case_id, complaint.reference AS case_reference,
                       COALESCE(citations.items, '[]'::jsonb) AS citations
                FROM core.messages m
                JOIN core.channels c ON c.channel_id = m.channel_id
                LEFT JOIN LATERAL (
                    SELECT r.response_id, r.body, r.status, r.grounding_score,
                           r.abstained, r.abstain_reason, r.policy_flags,
                           r.published_ref, r.created_at, r.created_by,
                           r.edited_by, r.submitted_at
                    FROM core.ai_inference_log i
                    JOIN core.responses r ON r.inference_run_id = i.inference_run_id
                    WHERE i.tenant_id = m.tenant_id
                      AND i.task = 'whatsapp_reply'
                      AND i.input_ref ->> 'message_id' = m.message_id::text
                      AND CAST(i.input_ref ->> 'occurred_at' AS timestamptz) = m.occurred_at
                    ORDER BY i.created_at DESC
                    LIMIT 1
                ) reply ON true
                LEFT JOIN LATERAL (
                    SELECT cp.case_id, cs.reference
                    FROM core.complaints cp
                    JOIN core.cases cs ON cs.case_id = cp.case_id
                    WHERE cp.tenant_id = m.tenant_id
                      AND cp.message_id = m.message_id
                      AND cp.occurred_at = m.occurred_at
                    LIMIT 1
                ) complaint ON true
                LEFT JOIN LATERAL (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'seq', rc.seq,
                            'title_ar', d.title_ar,
                            'title_en', d.title_en,
                            'heading_path', dc.heading_path,
                            'quoted_text', rc.quoted_text,
                            'entailment', rc.entailment
                        ) ORDER BY rc.seq
                    ) AS items
                    FROM core.response_citations rc
                    JOIN core.documents d ON d.document_id = rc.document_id
                    JOIN core.doc_chunks dc ON dc.chunk_id = rc.chunk_id
                    WHERE rc.response_id = reply.response_id
                ) citations ON true
                WHERE m.tenant_id = :tenant_id AND c.code = 'whatsapp'
                ORDER BY m.occurred_at DESC
                LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "limit": limit},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def update_whatsapp_reply(
    session: AsyncSession,
    *,
    response_id: UUID,
    tenant_id: UUID,
    editor_user_id: UUID,
    body: str,
) -> UpdatedReply:
    normalized_body = body.strip()
    row = (
        await session.execute(
            text(
                """
                SELECT response_id, body, status::text
                FROM core.responses
                WHERE response_id = :response_id AND tenant_id = :tenant_id
                FOR UPDATE
                """
            ),
            {"response_id": response_id, "tenant_id": tenant_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Reply not found")
    if row["status"] not in {"draft", "pending_approval"}:
        raise ValueError(f"Reply cannot be edited from status {row['status']}")

    previous_body = str(row["body"])
    edit_distance = sum(
        left != right for left, right in zip(previous_body, normalized_body, strict=False)
    ) + abs(len(previous_body) - len(normalized_body))
    await session.execute(
        text(
            """
            UPDATE core.responses
            SET body = :body, status = 'draft', edited_by = :editor_user_id,
                created_by = COALESCE(created_by, :editor_user_id),
                edit_distance = :edit_distance, submitted_at = NULL
            WHERE response_id = :response_id AND tenant_id = :tenant_id
            """
        ),
        {
            "body": normalized_body,
            "editor_user_id": editor_user_id,
            "edit_distance": edit_distance,
            "response_id": response_id,
            "tenant_id": tenant_id,
        },
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(editor_user_id),
        action="response.edit",
        object_type="response",
        object_id=str(response_id),
        before_state={"status": row["status"], "body": previous_body},
        after_state={"status": "draft", "body": normalized_body},
    )
    await session.commit()
    return UpdatedReply(
        response_id=response_id,
        body=normalized_body,
        status="draft",
        edit_distance=edit_distance,
    )


async def submit_whatsapp_reply(
    session: AsyncSession,
    *,
    response_id: UUID,
    tenant_id: UUID,
    submitter_user_id: UUID,
) -> SubmittedReply:
    row = (
        await session.execute(
            text(
                """
                SELECT response_id, status::text, body, abstained, policy_flags,
                       grounding_score
                FROM core.responses
                WHERE response_id = :response_id AND tenant_id = :tenant_id
                FOR UPDATE
                """
            ),
            {"response_id": response_id, "tenant_id": tenant_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Reply not found")
    if row["status"] != "draft":
        raise ValueError(f"Reply cannot be submitted from status {row['status']}")
    if len(str(row["body"]).strip()) < 10:
        raise ValueError("Reply is too short to submit")
    if row["abstained"] or row["policy_flags"] or float(row["grounding_score"] or 0.0) < 0.6:
        raise ValueError("Reply did not pass grounding and policy checks")
    await session.execute(
        text(
            """
            UPDATE core.responses
            SET status = 'pending_approval', submitted_at = now(),
                created_by = COALESCE(created_by, :submitter),
                edited_by = COALESCE(edited_by, :submitter)
            WHERE response_id = :response_id AND tenant_id = :tenant_id
            """
        ),
        {"response_id": response_id, "tenant_id": tenant_id, "submitter": submitter_user_id},
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(submitter_user_id),
        action="response.submit",
        object_type="response",
        object_id=str(response_id),
        before_state={"status": "draft"},
        after_state={"status": "pending_approval"},
    )
    await session.commit()
    return SubmittedReply(response_id=response_id, status="pending_approval")


async def process_whatsapp_message(
    session: AsyncSession,
    *,
    message: WhatsAppMessage,
    metadata: WhatsAppMetadata,
    settings: Settings,
) -> MessageProcessingResult:
    persisted = await ingest_whatsapp_message(
        session,
        message=message,
        metadata=metadata,
        settings=settings,
    )
    if persisted is None:
        return MessageProcessingResult(
            message_id=None,
            response_id=None,
            status=f"awaiting_{message.type}_processing",
        )
    if persisted.duplicate:
        await session.rollback()
        return MessageProcessingResult(
            message_id=persisted.message_id,
            response_id=None,
            status="duplicate",
        )
    await session.commit()
    return await process_persisted_whatsapp_message(
        session,
        message_id=persisted.message_id,
        occurred_at=persisted.occurred_at,
        settings=settings,
    )


async def ingest_whatsapp_message(
    session: AsyncSession,
    *,
    message: WhatsAppMessage,
    metadata: WhatsAppMetadata,
    settings: Settings,
) -> PersistedMessage | None:
    content = message.textual_content
    if not content:
        return None
    return await persist_inbound_message(
        session,
        tenant_code=settings.whatsapp_tenant_code,
        source_handle=settings.whatsapp_source_handle,
        tenant_pepper=settings.tenant_pepper,
        pii_encryption_key=settings.pii_encryption_key,
        inbound=InboundMessage(
            external_id=message.message_id,
            sender_native_id=message.sender,
            occurred_at=message.occurred_at,
            text=content,
            phone_number_id=metadata.phone_number_id,
            message_type=message.type,
        ),
    )


async def process_persisted_whatsapp_message(
    session: AsyncSession,
    *,
    message_id: UUID,
    occurred_at: datetime,
    settings: Settings,
) -> MessageProcessingResult:
    persisted = (
        await session.execute(
            text(
                """
                SELECT m.message_id, m.tenant_id, m.occurred_at, m.raw_text,
                       m.lang_primary::text, m.external_id,
                       pgp_sym_decrypt(v.native_id_enc, :encryption_key) AS recipient
                FROM core.messages m
                JOIN restricted.pii_vault v
                  ON v.author_pseudonym = m.author_pseudonym
                WHERE m.message_id = :message_id AND m.occurred_at = :occurred_at
                """
            ),
            {
                "message_id": message_id,
                "occurred_at": occurred_at,
                "encryption_key": settings.pii_encryption_key,
            },
        )
    ).mappings().one_or_none()
    if persisted is None:
        raise LookupError("Persisted WhatsApp message was not found")
    existing_response = (
        await session.execute(
            text(
                """
                SELECT r.response_id, r.abstained
                FROM core.ai_inference_log i
                JOIN core.responses r ON r.inference_run_id = i.inference_run_id
                WHERE i.tenant_id = :tenant_id
                  AND i.task = 'whatsapp_reply'
                  AND i.input_ref ->> 'message_id' = :message_id
                  AND i.input_ref ->> 'occurred_at' = :occurred_at
                ORDER BY i.created_at DESC
                LIMIT 1
                """
            ),
            {
                "tenant_id": persisted["tenant_id"],
                "message_id": str(message_id),
                "occurred_at": occurred_at.isoformat(),
            },
        )
    ).mappings().one_or_none()
    if existing_response:
        return MessageProcessingResult(
            message_id=message_id,
            response_id=existing_response["response_id"],
            status="received" if existing_response["abstained"] else "draft_ready",
        )

    language = persisted["lang_primary"]
    generated = None
    if settings.whatsapp_reply_mode in {"draft", "acknowledge"}:
        generated = await generate_grounded_reply(
            session,
            tenant_id=persisted["tenant_id"],
            message_id=persisted["message_id"],
            message_occurred_at=persisted["occurred_at"],
            citizen_text=persisted["raw_text"],
            language="en" if language == "en" else "ar",
            retrieval_gate=settings.rag_hybrid_gate,
            settings=settings,
        )
    case_id = await create_case_from_message(
        session,
        tenant_id=persisted["tenant_id"],
        message_id=persisted["message_id"],
        occurred_at=persisted["occurred_at"],
        raw_text=persisted["raw_text"],
    )
    if generated is not None:
        await session.execute(
            text(
                "UPDATE core.responses SET case_id = :case_id "
                "WHERE response_id = :response_id AND tenant_id = :tenant_id"
            ),
            {
                "case_id": case_id,
                "response_id": generated.response_id,
                "tenant_id": persisted["tenant_id"],
            },
        )
    await write_audit(
        session,
        tenant_id=str(persisted["tenant_id"]),
        actor_user_id=None,
        actor_type="worker",
        action="whatsapp.message.ingest",
        object_type="message",
        object_id=str(persisted["message_id"]),
        after_state={
            "channel": "whatsapp",
            "draft_created": generated is not None,
            "abstained": generated.abstained if generated else None,
            "case_id": str(case_id),
        },
    )
    acknowledgement_id = None
    if settings.whatsapp_reply_mode == "acknowledge":
        acknowledgement = ACKNOWLEDGEMENT_EN if language == "en" else ACKNOWLEDGEMENT_AR
        receipt = await WhatsAppClient(settings).send_text(
            recipient=persisted["recipient"],
            body=acknowledgement,
            reply_to_message_id=persisted["external_id"],
        )
        acknowledgement_id = receipt.external_id
        await write_audit(
            session,
            tenant_id=str(persisted["tenant_id"]),
            actor_user_id=None,
            actor_type="worker",
            action="whatsapp.acknowledgement.send",
            object_type="message",
            object_id=str(persisted["message_id"]),
            after_state={"simulated": receipt.simulated},
        )
    await session.commit()
    return MessageProcessingResult(
        message_id=persisted["message_id"],
        response_id=generated.response_id if generated else None,
        status="draft_ready" if generated and not generated.abstained else "received",
        acknowledgement_id=acknowledgement_id,
    )


async def record_whatsapp_status(
    session: AsyncSession,
    *,
    status_event: WhatsAppStatus,
    settings: Settings,
) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT r.response_id, r.tenant_id
                FROM core.responses r
                JOIN core.tenants t ON t.tenant_id = r.tenant_id
                WHERE t.code = :tenant_code
                  AND r.published_ref = :published_ref
                LIMIT 1
                """
            ),
            {
                "tenant_code": settings.whatsapp_tenant_code,
                "published_ref": status_event.id,
            },
        )
    ).mappings().one_or_none()
    if row is None:
        return
    await write_audit(
        session,
        tenant_id=str(row["tenant_id"]),
        actor_user_id=None,
        actor_type="worker",
        action=f"whatsapp.delivery.{status_event.status}",
        object_type="response",
        object_id=str(row["response_id"]),
        outcome="error" if status_event.status == "failed" else "success",
        after_state={"error_count": len(status_event.errors)},
    )
    await session.commit()


async def approve_and_deliver_reply(
    session: AsyncSession,
    *,
    response_id: UUID,
    tenant_id: UUID,
    approver_user_id: UUID,
    settings: Settings,
    comment: str | None,
) -> ApprovedDelivery:
    row = (
        await session.execute(
            text(
                """
                SELECT r.response_id, r.status::text, r.body, r.grounding_score,
                       r.abstained, r.policy_flags, r.published_ref,
                       r.created_by, r.edited_by,
                       m.external_id AS inbound_external_id,
                       pgp_sym_decrypt(v.native_id_enc, :encryption_key) AS recipient
                FROM core.responses r
                JOIN core.ai_inference_log i
                  ON i.inference_run_id = r.inference_run_id
                JOIN core.messages m
                  ON m.message_id = CAST(i.input_ref ->> 'message_id' AS uuid)
                 AND m.occurred_at = CAST(i.input_ref ->> 'occurred_at' AS timestamptz)
                JOIN restricted.pii_vault v
                  ON v.author_pseudonym = m.author_pseudonym
                WHERE r.response_id = :response_id
                  AND r.tenant_id = :tenant_id
                FOR UPDATE OF r
                """
            ),
            {
                "response_id": response_id,
                "tenant_id": tenant_id,
                "encryption_key": settings.pii_encryption_key,
            },
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Reply not found")
    if row["status"] == "published" and row["published_ref"]:
        return ApprovedDelivery(
            response_id=response_id,
            status="published",
            published_ref=row["published_ref"],
            simulated=str(row["published_ref"]).startswith("simulated:"),
        )
    if row["status"] != "pending_approval":
        raise ValueError(f"Reply cannot be delivered from status {row['status']}")
    if approver_user_id in {row["created_by"], row["edited_by"]}:
        raise ValueError("Maker-checker violation: the draft author cannot approve it")
    if row["abstained"] or row["policy_flags"] or float(row["grounding_score"] or 0.0) < 0.6:
        raise ValueError("Reply did not pass grounding and policy checks")

    try:
        receipt = await WhatsAppClient(settings).send_text(
            recipient=row["recipient"],
            body=row["body"],
            reply_to_message_id=row["inbound_external_id"],
        )
    except WhatsAppDeliveryError:
        await write_audit(
            session,
            tenant_id=str(tenant_id),
            actor_user_id=str(approver_user_id),
            action="response.publish",
            object_type="response",
            object_id=str(response_id),
            outcome="error",
            after_state={"channel": "whatsapp"},
        )
        await session.commit()
        raise

    await session.execute(
        text(
            """
            UPDATE core.responses
            SET status = 'published', approved_by = :approver_user_id,
                approved_at = COALESCE(approved_at, now()), published_at = now(),
                published_ref = :published_ref
            WHERE response_id = :response_id AND tenant_id = :tenant_id
            """
        ),
        {
            "response_id": response_id,
            "tenant_id": tenant_id,
            "approver_user_id": approver_user_id,
            "published_ref": receipt.external_id,
        },
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(approver_user_id),
        action="response.publish",
        object_type="response",
        object_id=str(response_id),
        before_state={"status": row["status"]},
        after_state={
            "status": "published",
            "channel": "whatsapp",
            "simulated": receipt.simulated,
            "comment": comment,
        },
    )
    await session.commit()
    return ApprovedDelivery(
        response_id=response_id,
        status="published",
        published_ref=receipt.external_id,
        simulated=receipt.simulated,
    )


def message_job_payload(message: PersistedMessage) -> dict[str, str]:
    return {
        "message_id": str(message.message_id),
        "occurred_at": message.occurred_at.isoformat(),
    }


def status_job_payload(status: WhatsAppStatus) -> dict[str, object]:
    return {
        "id": status.id,
        "status": status.status,
        "timestamp": status.timestamp,
        "errors": status.errors,
    }
