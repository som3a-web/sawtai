from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.auth.service import UserContext, get_current_user
from sawtai.database import get_session
from sawtai.notifications.service import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("")
async def notifications(
    limit: int = Query(default=50, ge=1, le=200),
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return await list_notifications(
        session,
        tenant_id=UUID(user.tenant_id),
        user_id=UUID(user.user_id),
        limit=limit,
    )


@router.post("/{notification_id}/read")
async def read_notification(
    notification_id: UUID,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await mark_notification_read(
            session,
            tenant_id=UUID(user.tenant_id),
            user_id=UUID(user.user_id),
            event_id=notification_id,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return {"status": "read"}


@router.post("/read-all")
async def read_all_notifications(
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    count = await mark_all_notifications_read(
        session,
        tenant_id=UUID(user.tenant_id),
        user_id=UUID(user.user_id),
    )
    return {"status": "read", "count": count}
