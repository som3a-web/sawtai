"""Password authentication, JWT sessions, and role-based authorisation."""

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.audit.service import write_audit
from sawtai.config import Settings, get_settings
from sawtai.database import get_session

security = HTTPBearer(auto_error=False)
password_hasher = PasswordHasher()


@dataclass(frozen=True)
class UserContext:
    user_id: str
    tenant_id: str
    email: str
    display_name_ar: str
    display_name_en: str
    org_unit_id: str | None
    roles: tuple[str, ...]
    permissions: frozenset[str]
    mfa_enrolled: bool


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def _encode_token(
    *,
    user_id: str,
    tenant_id: str,
    token_type: Literal["access", "refresh"],
    lifetime: timedelta,
    settings: Settings,
    extra: dict[str, Any] | None = None,
) -> tuple[str, str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + lifetime
    token_id = str(uuid4())
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "type": token_type,
        "jti": token_id,
        "iat": now,
        "exp": expires_at,
    }
    payload.update(extra or {})
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), token_id, expires_at


def decode_token(token: str, *, expected_type: str, settings: Settings) -> dict[str, Any]:
    try:
        payload = cast(
            dict[str, Any],
            jwt.decode(token, settings.jwt_secret, algorithms=["HS256"]),
        )
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


async def load_user_context(
    session: AsyncSession,
    *,
    user_id: UUID,
    tenant_id: UUID,
) -> UserContext | None:
    row = (
        await session.execute(
            text(
                """
                SELECT u.user_id, u.tenant_id, u.email::text, u.display_name_ar,
                       u.display_name_en, u.org_unit_id, u.mfa_enrolled,
                       COALESCE(array_agg(DISTINCT r.code) FILTER (WHERE r.code IS NOT NULL), '{}') AS roles,
                       COALESCE(jsonb_agg(DISTINCT p.permission) FILTER (WHERE p.permission IS NOT NULL), '[]') AS permissions
                FROM core.users u
                LEFT JOIN core.user_roles ur ON ur.user_id = u.user_id
                LEFT JOIN core.roles r ON r.role_id = ur.role_id
                LEFT JOIN LATERAL jsonb_array_elements_text(r.permissions) p(permission) ON true
                WHERE u.user_id = :user_id AND u.tenant_id = :tenant_id AND u.is_active
                GROUP BY u.user_id
                """
            ),
            {"user_id": user_id, "tenant_id": tenant_id},
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    return UserContext(
        user_id=str(row["user_id"]),
        tenant_id=str(row["tenant_id"]),
        email=str(row["email"]),
        display_name_ar=str(row["display_name_ar"] or ""),
        display_name_en=str(row["display_name_en"] or ""),
        org_unit_id=str(row["org_unit_id"]) if row["org_unit_id"] else None,
        roles=tuple(sorted(row["roles"])),
        permissions=frozenset(row["permissions"]),
        mfa_enrolled=bool(row["mfa_enrolled"]),
    )


async def authenticate_user(
    session: AsyncSession,
    *,
    tenant_code: str,
    email: str,
    password: str,
) -> UserContext | None:
    row = (
        await session.execute(
            text(
                """
                SELECT u.user_id, u.tenant_id, u.password_hash
                FROM core.users u
                JOIN core.tenants t ON t.tenant_id = u.tenant_id
                WHERE t.code = :tenant_code AND lower(u.email::text) = lower(:email)
                  AND u.is_active
                """
            ),
            {"tenant_code": tenant_code, "email": email.strip()},
        )
    ).mappings().one_or_none()
    if row is None or not verify_password(row["password_hash"], password):
        return None
    return await load_user_context(
        session,
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
    )


async def issue_token_pair(
    user: UserContext,
    settings: Settings,
    session: AsyncSession,
) -> tuple[str, str, int]:
    access, _, _ = _encode_token(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        token_type="access",
        lifetime=timedelta(minutes=settings.access_token_minutes),
        settings=settings,
        extra={"roles": user.roles, "permissions": sorted(user.permissions)},
    )
    refresh, refresh_id, expires_at = _encode_token(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        token_type="refresh",
        lifetime=timedelta(days=settings.refresh_token_days),
        settings=settings,
    )
    await write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        action="auth.refresh.issue",
        object_type="auth_session",
        object_id=refresh_id,
        after_state={
            "token_hash": hashlib.sha256(refresh.encode()).hexdigest(),
            "expires_at": expires_at.isoformat(),
        },
    )
    return access, refresh, settings.access_token_minutes * 60


async def rotate_refresh_token(
    token: str,
    *,
    session: AsyncSession,
    settings: Settings,
) -> tuple[UserContext, str, str, int]:
    payload = decode_token(token, expected_type="refresh", settings=settings)
    refresh_id = str(payload["jti"])
    ledger = (
        await session.execute(
            text(
                """
                SELECT action, after_state
                FROM core.audit_log
                WHERE tenant_id = :tenant_id AND object_id = :session_id
                  AND object_type = 'auth_session'
                ORDER BY occurred_at DESC, audit_id DESC
                LIMIT 1
                """
            ),
            {
                "tenant_id": UUID(str(payload["tenant_id"])),
                "session_id": UUID(refresh_id),
            },
        )
    ).mappings().one_or_none()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if (
        ledger is None
        or ledger["action"] != "auth.refresh.issue"
        or ledger["after_state"].get("token_hash") != token_hash
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session was revoked")
    user = await load_user_context(
        session,
        user_id=UUID(str(payload["sub"])),
        tenant_id=UUID(str(payload["tenant_id"])),
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")
    await write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        action="auth.refresh.revoke",
        object_type="auth_session",
        object_id=refresh_id,
        after_state={"reason": "rotated"},
    )
    access, refresh, expires_in = await issue_token_pair(user, settings, session)
    return user, access, refresh, expires_in


async def revoke_refresh_token(
    token: str | None,
    settings: Settings,
    session: AsyncSession,
) -> None:
    if not token:
        return
    try:
        payload = decode_token(token, expected_type="refresh", settings=settings)
    except HTTPException:
        return
    await write_audit(
        session,
        tenant_id=str(payload["tenant_id"]),
        actor_user_id=str(payload["sub"]),
        action="auth.refresh.revoke",
        object_type="auth_session",
        object_id=str(payload["jti"]),
        after_state={"reason": "logout"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> UserContext:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials, expected_type="access", settings=settings)
    user = await load_user_context(
        session,
        user_id=UUID(str(payload["sub"])),
        tenant_id=UUID(str(payload["tenant_id"])),
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")
    return user


def has_permission(user: UserContext, permission: str) -> bool:
    namespace = permission.partition(":")[0]
    return permission in user.permissions or f"{namespace}:*" in user.permissions


def require(*permissions: str) -> Callable[..., Awaitable[UserContext]]:
    async def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        missing = [permission for permission in permissions if not has_permission(user, permission)]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {', '.join(sorted(missing))}",
            )
        return user

    return dependency
