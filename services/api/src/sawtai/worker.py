from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from sawtai.config import get_settings


async def heartbeat(_: dict[str, Any]) -> None:
    """Minimal cron hook proving the worker/scheduler process is live."""


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions = [heartbeat]
    cron_jobs = [cron("sawtai.worker.heartbeat", minute={0, 15, 30, 45})]
    max_jobs = 4
