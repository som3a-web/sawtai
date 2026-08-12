import json
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.auth.service import UserContext, require
from sawtai.channels.models import ReplyApprovalRequest, ReplyUpdateRequest, WhatsAppWebhook
from sawtai.channels.security import verify_meta_signature
from sawtai.channels.service import (
    approve_and_deliver_reply,
    ingest_whatsapp_message,
    list_whatsapp_inbox,
    message_job_payload,
    status_job_payload,
    submit_whatsapp_reply,
    update_whatsapp_reply,
)
from sawtai.channels.whatsapp import WhatsAppDeliveryError
from sawtai.config import Settings, get_settings
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1/channels/whatsapp", tags=["whatsapp"])


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    mode: str = Query(alias="hub.mode"),
    verify_token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
    settings: Settings = Depends(get_settings),
) -> str:
    if not settings.whatsapp_verify_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook is not configured")
    if mode != "subscribe" or verify_token != settings.whatsapp_verify_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook verification failed")
    return challenge


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    signature: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    body = await request.body()
    if settings.whatsapp_signature_required or signature:
        if not verify_meta_signature(body, signature, settings.whatsapp_app_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")
    try:
        webhook = WhatsAppWebhook.model_validate(json.loads(body))
    except (json.JSONDecodeError, ValidationError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload") from error
    if webhook.object != "whatsapp_business_account":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported webhook object")

    messages, statuses = webhook.events()
    persisted_messages = []
    for message, metadata in messages:
        persisted = await ingest_whatsapp_message(
            session,
            message=message,
            metadata=metadata,
            settings=settings,
        )
        if persisted is not None:
            persisted_messages.append(persisted)
    await session.commit()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        for persisted in persisted_messages:
            await redis.enqueue_job(
                "process_whatsapp_message_job",
                message_job_payload(persisted),
                _job_id=f"whatsapp:message:{persisted.message_id}",
            )
        for status_event in statuses:
            await redis.enqueue_job(
                "process_whatsapp_status_job",
                status_job_payload(status_event),
                _job_id=(
                    f"whatsapp:status:{status_event.id}:"
                    f"{status_event.status}:{status_event.timestamp}"
                ),
            )
    finally:
        await redis.aclose()
    return {
        "status": "accepted",
        "messages": len(persisted_messages),
        "unsupported_messages": len(messages) - len(persisted_messages),
        "delivery_updates": len(statuses),
    }


@router.get("/status")
async def whatsapp_status(
    user: UserContext = Depends(require("message:read")),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return {
        "tenant_id": user.tenant_id,
        "configured": bool(settings.whatsapp_phone_number_id),
        "signature_required": settings.whatsapp_signature_required,
        "delivery_mode": settings.whatsapp_delivery_mode,
        "reply_mode": settings.whatsapp_reply_mode,
        "voice_ready": False,
    }


@router.get("/inbox")
async def whatsapp_inbox(
    limit: int = Query(default=50, ge=1, le=200),
    user: UserContext = Depends(require("message:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    items = await list_whatsapp_inbox(
        session,
        tenant_id=UUID(user.tenant_id),
        limit=limit,
    )
    return {"items": items, "count": len(items)}


@router.post("/replies/{response_id}/approve-and-send")
async def approve_reply(
    response_id: UUID,
    payload: ReplyApprovalRequest,
    user: UserContext = Depends(require("draft:approve")),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        delivered = await approve_and_deliver_reply(
            session,
            response_id=response_id,
            tenant_id=UUID(user.tenant_id),
            approver_user_id=UUID(user.user_id),
            settings=settings,
            comment=payload.comment,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except WhatsAppDeliveryError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    return {
        "response_id": delivered.response_id,
        "status": delivered.status,
        "published_ref": delivered.published_ref,
        "simulated": delivered.simulated,
    }


@router.post("/replies/{response_id}/submit")
async def submit_reply(
    response_id: UUID,
    user: UserContext = Depends(require("draft:submit")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        submitted = await submit_whatsapp_reply(
            session,
            response_id=response_id,
            tenant_id=UUID(user.tenant_id),
            submitter_user_id=UUID(user.user_id),
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {"response_id": submitted.response_id, "status": submitted.status}


@router.patch("/replies/{response_id}")
async def update_reply(
    response_id: UUID,
    payload: ReplyUpdateRequest,
    user: UserContext = Depends(require("draft:edit")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        updated = await update_whatsapp_reply(
            session,
            response_id=response_id,
            tenant_id=UUID(user.tenant_id),
            editor_user_id=UUID(user.user_id),
            body=payload.body,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {
        "response_id": updated.response_id,
        "body": updated.body,
        "status": updated.status,
        "edit_distance": updated.edit_distance,
    }
