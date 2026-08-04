"""Prototype authentication and role-based authorisation facade."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

DEMO_TOKEN = "sawtai-demo-token"
security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class UserContext:
    user_id: str
    tenant_id: str
    display_name_ar: str
    display_name_en: str
    roles: tuple[str, ...]
    permissions: frozenset[str]


DEMO_USER = UserContext(
    user_id="00000000-0000-0000-0000-000000000201",
    tenant_id="00000000-0000-0000-0000-000000000001",
    display_name_ar="مريم الكتبي",
    display_name_en="Maryam Al Ketbi",
    roles=("comms_officer", "crisis_lead"),
    permissions=frozenset(
        {
            "analytics:read",
            "message:read",
            "message:review",
            "draft:create",
            "draft:edit",
            "draft:submit",
            "alert:read",
            "alert:manage",
            "audit:read",
            "data:read",
        }
    ),
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserContext:
    if credentials is None or credentials.credentials == DEMO_TOKEN:
        return DEMO_USER
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")


def require(*permissions: str) -> Callable[..., Awaitable[UserContext]]:
    async def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        missing = set(permissions) - user.permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(sorted(missing))}",
            )
        return user

    return dependency
