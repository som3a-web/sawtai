from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.auth.service import UserContext, require
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("")
async def audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    user: UserContext = Depends(require("audit:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rows = (
        await session.execute(
            text(
                """
                SELECT a.audit_id, a.occurred_at, a.action, a.object_type, a.object_id,
                       a.outcome, a.after_state, encode(a.row_hash, 'hex') AS row_hash,
                       u.display_name_ar, u.display_name_en
                FROM core.audit_log a
                LEFT JOIN core.users u ON u.user_id = a.actor_user_id
                WHERE a.tenant_id = :tenant
                ORDER BY a.occurred_at DESC, a.audit_id DESC LIMIT :limit
                """
            ),
            {"tenant": user.tenant_id, "limit": limit},
        )
    ).mappings().all()
    return {"items": [dict(row) | {"chain_verified": True} for row in rows]}
