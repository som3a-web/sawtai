"""Append-only audit write facade."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def write_audit(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor_user_id: str | None,
    action: str,
    object_type: str,
    object_id: str | None,
    actor_type: str = "user",
    outcome: str = "success",
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> None:
    previous = await session.execute(
        text(
            "SELECT row_hash FROM core.audit_log "
            "WHERE tenant_id = :tenant_id ORDER BY occurred_at DESC, audit_id DESC LIMIT 1"
        ),
        {"tenant_id": UUID(tenant_id)},
    )
    previous_hash = previous.scalar_one_or_none()
    occurred_at = datetime.now(UTC)
    canonical = json.dumps(
        {
            "tenant_id": tenant_id,
            "actor_user_id": actor_user_id,
            "actor_type": actor_type,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "outcome": outcome,
            "occurred_at": occurred_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    row_hash = hashlib.sha256((previous_hash or b"") + canonical).digest()
    await session.execute(
        text(
            """
            INSERT INTO core.audit_log (
                tenant_id, occurred_at, actor_user_id, actor_type, action,
                object_type, object_id, outcome, before_state, after_state,
                prev_hash, row_hash
            ) VALUES (
                :tenant_id, :occurred_at, :actor_user_id, :actor_type, :action,
                :object_type, :object_id, :outcome,
                CAST(:before_state AS jsonb), CAST(:after_state AS jsonb),
                :prev_hash, :row_hash
            )
            """
        ),
        {
            "tenant_id": UUID(tenant_id),
            "occurred_at": occurred_at,
            "actor_user_id": UUID(actor_user_id) if actor_user_id else None,
            "actor_type": actor_type,
            "action": action,
            "object_type": object_type,
            "object_id": UUID(object_id) if object_id else None,
            "outcome": outcome,
            "before_state": json.dumps(before_state) if before_state else None,
            "after_state": json.dumps(after_state) if after_state else None,
            "prev_hash": previous_hash,
            "row_hash": row_hash,
        },
    )
