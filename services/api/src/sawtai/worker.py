from datetime import datetime
from typing import Any
from uuid import UUID

from arq.connections import RedisSettings
from arq.cron import cron

from sawtai.channels.models import WhatsAppStatus
from sawtai.channels.service import process_persisted_whatsapp_message, record_whatsapp_status
from sawtai.config import get_settings
from sawtai.database import session_factory
from sawtai.notifications.service import evaluate_notification_rules


async def heartbeat(_: dict[str, Any]) -> None:
    """Minimal cron hook proving the worker/scheduler process is live."""


async def process_whatsapp_message_job(_: dict[str, Any], payload: dict[str, Any]) -> None:
    async with session_factory() as session:
        await process_persisted_whatsapp_message(
            session,
            message_id=UUID(payload["message_id"]),
            occurred_at=datetime.fromisoformat(payload["occurred_at"]),
            settings=get_settings(),
        )


async def process_whatsapp_status_job(_: dict[str, Any], payload: dict[str, Any]) -> None:
    status = WhatsAppStatus.model_validate(payload)
    async with session_factory() as session:
        await record_whatsapp_status(session, status_event=status, settings=get_settings())


async def evaluate_notification_rules_job(_: dict[str, Any]) -> None:
    async with session_factory() as session:
        await evaluate_notification_rules(session)
        await session.commit()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions = [
        heartbeat,
        process_whatsapp_message_job,
        process_whatsapp_status_job,
        evaluate_notification_rules_job,
    ]
    cron_jobs = [
        cron("sawtai.worker.heartbeat", minute={0, 15, 30, 45}),
        cron("sawtai.worker.evaluate_notification_rules_job", minute=set(range(0, 60, 5))),
    ]
    max_jobs = 4
