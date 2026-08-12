from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.audit.service import write_audit
from sawtai.auth.service import (
    UserContext,
    authenticate_user,
    get_current_user,
    hash_password,
    issue_token_pair,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_password,
)
from sawtai.config import Settings, get_settings
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
REFRESH_COOKIE = "sawtai_refresh"


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    tenant_code: str = Field(default="shj-demo", min_length=2, max_length=64)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def user_payload(user: UserContext) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "display_name_ar": user.display_name_ar,
        "display_name_en": user.display_name_en,
        "org_unit_id": user.org_unit_id,
        "roles": user.roles,
        "permissions": sorted(user.permissions),
        "mfa_enrolled": user.mfa_enrolled,
    }


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.environment not in {"development", "test"},
        samesite="lax",
        path="/api/v1/auth",
    )


@router.post("/token")
async def token(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    tenant = (
        await session.execute(
            text("SELECT tenant_id FROM core.tenants WHERE code = :code"),
            {"code": payload.tenant_code},
        )
    ).scalar_one_or_none()
    user = await authenticate_user(
        session,
        tenant_code=payload.tenant_code,
        email=payload.email,
        password=payload.password,
    )
    if user is None:
        if tenant is not None:
            await write_audit(
                session,
                tenant_id=str(tenant),
                actor_user_id=None,
                actor_type="system",
                action="auth.login",
                object_type="user",
                object_id=None,
                outcome="denied",
                after_state={"email": payload.email.strip().lower()},
            )
            await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token, refresh_token, expires_in = await issue_token_pair(user, settings, session)
    set_refresh_cookie(response, refresh_token, settings)
    await session.execute(
        text("UPDATE core.users SET last_login_at = now() WHERE user_id = :user_id"),
        {"user_id": user.user_id},
    )
    await write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        action="auth.login",
        object_type="user",
        object_id=user.user_id,
    )
    await session.commit()
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": user_payload(user),
    }


@router.post("/refresh")
async def refresh(
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session missing")
    user, access_token, new_refresh, expires_in = await rotate_refresh_token(
        refresh_token,
        session=session,
        settings=settings,
    )
    await session.commit()
    set_refresh_cookie(response, new_refresh, settings)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": user_payload(user),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> None:
    await revoke_refresh_token(refresh_token, settings, session)
    await session.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me")
async def me(user: UserContext = Depends(get_current_user)) -> dict[str, object]:
    return user_payload(user)


@router.post("/password/change")
async def change_password(
    payload: PasswordChangeRequest,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    current_hash = (
        await session.execute(
            text("SELECT password_hash FROM core.users WHERE user_id = :user_id"),
            {"user_id": user.user_id},
        )
    ).scalar_one()
    if not verify_password(current_hash, payload.current_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    await session.execute(
        text("UPDATE core.users SET password_hash = :password WHERE user_id = :user_id"),
        {"password": hash_password(payload.new_password), "user_id": user.user_id},
    )
    await write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        action="user.password_change",
        object_type="user",
        object_id=user.user_id,
    )
    await session.commit()
    return {"status": "password_changed"}
