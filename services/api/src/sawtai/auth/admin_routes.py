"""Tenant-scoped user and role administration."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.audit.service import write_audit
from sawtai.auth.service import UserContext, hash_password, require
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1", tags=["administration"])


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name_ar: str = Field(min_length=2, max_length=200)
    display_name_en: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=256)
    role_codes: list[str] = Field(min_length=1, max_length=5)
    org_unit_id: UUID | None = None
    mfa_enrolled: bool = False


class RoleAssignmentRequest(BaseModel):
    role_codes: list[str] = Field(min_length=1, max_length=5)
    org_unit_id: UUID | None = None


class PasswordResetRequest(BaseModel):
    temporary_password: str = Field(min_length=12, max_length=256)


class UserStatusRequest(BaseModel):
    is_active: bool


def _user_dict(row: object) -> dict[str, object]:
    values = row._mapping  # type: ignore[attr-defined]
    return {
        "user_id": str(values["user_id"]),
        "email": str(values["email"]),
        "display_name_ar": values["display_name_ar"],
        "display_name_en": values["display_name_en"],
        "org_unit_id": str(values["org_unit_id"]) if values["org_unit_id"] else None,
        "is_active": values["is_active"],
        "mfa_enrolled": values["mfa_enrolled"],
        "last_login_at": values["last_login_at"],
        "roles": values["roles"],
    }


async def _validate_roles(session: AsyncSession, role_codes: list[str]) -> dict[str, UUID]:
    normalized = sorted(set(role_codes))
    rows = (
        await session.execute(
            text("SELECT role_id, code FROM core.roles WHERE code = ANY(:codes)"),
            {"codes": normalized},
        )
    ).mappings().all()
    roles = {str(row["code"]): row["role_id"] for row in rows}
    missing = set(normalized) - roles.keys()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown roles: {', '.join(sorted(missing))}",
        )
    return roles


@router.get("/roles")
async def list_roles(
    _: UserContext = Depends(require("role:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rows = (
        await session.execute(
            text(
                "SELECT role_id, code, name_ar, name_en, permissions "
                "FROM core.roles ORDER BY code"
            )
        )
    ).mappings().all()
    return {
        "items": [
            {
                "role_id": str(row["role_id"]),
                "code": row["code"],
                "name_ar": row["name_ar"],
                "name_en": row["name_en"],
                "permissions": row["permissions"],
            }
            for row in rows
        ]
    }


@router.get("/users")
async def list_users(
    user: UserContext = Depends(require("user:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rows = (
        await session.execute(
            text(
                """
                SELECT u.user_id, u.email::text, u.display_name_ar, u.display_name_en,
                       u.org_unit_id, u.is_active, u.mfa_enrolled, u.last_login_at,
                       COALESCE(array_agg(r.code ORDER BY r.code) FILTER (WHERE r.code IS NOT NULL), '{}') AS roles
                FROM core.users u
                LEFT JOIN core.user_roles ur ON ur.user_id = u.user_id
                LEFT JOIN core.roles r ON r.role_id = ur.role_id
                WHERE u.tenant_id = :tenant_id
                GROUP BY u.user_id
                ORDER BY u.created_at
                """
            ),
            {"tenant_id": UUID(user.tenant_id)},
        )
    ).all()
    return {"items": [_user_dict(row) for row in rows]}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateRequest,
    actor: UserContext = Depends(require("user:create")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    roles = await _validate_roles(session, payload.role_codes)
    org_unit_id = payload.org_unit_id or (UUID(actor.org_unit_id) if actor.org_unit_id else None)
    if org_unit_id is not None:
        valid_org = (
            await session.execute(
                text(
                    "SELECT 1 FROM core.org_units WHERE org_unit_id = :org AND tenant_id = :tenant"
                ),
                {"org": org_unit_id, "tenant": UUID(actor.tenant_id)},
            )
        ).scalar_one_or_none()
        if valid_org is None:
            raise HTTPException(status_code=422, detail="Organisation unit does not belong to tenant")
    try:
        user_id = (
            await session.execute(
                text(
                    """
                    INSERT INTO core.users (
                        tenant_id, email, display_name_ar, display_name_en,
                        org_unit_id, password_hash, mfa_enrolled
                    ) VALUES (
                        :tenant_id, :email, :name_ar, :name_en, :org_unit_id,
                        :password_hash, :mfa_enrolled
                    ) RETURNING user_id
                    """
                ),
                {
                    "tenant_id": UUID(actor.tenant_id),
                    "email": payload.email.strip().lower(),
                    "name_ar": payload.display_name_ar.strip(),
                    "name_en": payload.display_name_en.strip(),
                    "org_unit_id": org_unit_id,
                    "password_hash": hash_password(payload.password),
                    "mfa_enrolled": payload.mfa_enrolled,
                },
            )
        ).scalar_one()
        for role_id in roles.values():
            await session.execute(
                text(
                    """
                    INSERT INTO core.user_roles (user_id, role_id, org_unit_id, granted_by)
                    VALUES (:user_id, :role_id, :org_unit_id, :granted_by)
                    """
                ),
                {
                    "user_id": user_id,
                    "role_id": role_id,
                    "org_unit_id": org_unit_id,
                    "granted_by": UUID(actor.user_id),
                },
            )
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A user with this email already exists") from error
    await write_audit(
        session,
        tenant_id=actor.tenant_id,
        actor_user_id=actor.user_id,
        action="user.create",
        object_type="user",
        object_id=str(user_id),
        after_state={"email": payload.email.strip().lower(), "roles": sorted(roles)},
    )
    await session.commit()
    return {"user_id": str(user_id), "status": "created"}


@router.post("/users/{user_id}/roles")
async def replace_user_roles(
    user_id: UUID,
    payload: RoleAssignmentRequest,
    actor: UserContext = Depends(require("role:manage")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    target = (
        await session.execute(
            text("SELECT org_unit_id FROM core.users WHERE user_id = :user AND tenant_id = :tenant"),
            {"user": user_id, "tenant": UUID(actor.tenant_id)},
        )
    ).mappings().one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    roles = await _validate_roles(session, payload.role_codes)
    org_unit_id = payload.org_unit_id or target["org_unit_id"]
    previous = (
        await session.execute(
            text(
                "SELECT r.code FROM core.user_roles ur JOIN core.roles r ON r.role_id = ur.role_id "
                "WHERE ur.user_id = :user"
            ),
            {"user": user_id},
        )
    ).scalars().all()
    await session.execute(text("DELETE FROM core.user_roles WHERE user_id = :user"), {"user": user_id})
    for role_id in roles.values():
        await session.execute(
            text(
                """
                INSERT INTO core.user_roles (user_id, role_id, org_unit_id, granted_by)
                VALUES (:user, :role, :org, :actor)
                """
            ),
            {"user": user_id, "role": role_id, "org": org_unit_id, "actor": UUID(actor.user_id)},
        )
    await write_audit(
        session,
        tenant_id=actor.tenant_id,
        actor_user_id=actor.user_id,
        action="role.assign",
        object_type="user",
        object_id=str(user_id),
        before_state={"roles": sorted(previous)},
        after_state={"roles": sorted(roles)},
    )
    await session.commit()
    return {"user_id": str(user_id), "roles": sorted(roles)}


@router.post("/users/{user_id}/password")
async def reset_user_password(
    user_id: UUID,
    payload: PasswordResetRequest,
    actor: UserContext = Depends(require("user:manage")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    updated_user_id = (
        await session.execute(
            text(
                "UPDATE core.users SET password_hash = :password WHERE user_id = :user "
                "AND tenant_id = :tenant RETURNING user_id"
            ),
            {
                "password": hash_password(payload.temporary_password),
                "user": user_id,
                "tenant": UUID(actor.tenant_id),
            },
        )
    ).scalar_one_or_none()
    if updated_user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    await write_audit(
        session,
        tenant_id=actor.tenant_id,
        actor_user_id=actor.user_id,
        action="user.password_reset",
        object_type="user",
        object_id=str(user_id),
    )
    await session.commit()
    return {"status": "password_reset"}


@router.patch("/users/{user_id}/status")
async def set_user_status(
    user_id: UUID,
    payload: UserStatusRequest,
    actor: UserContext = Depends(require("user:manage")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    if user_id == UUID(actor.user_id) and not payload.is_active:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")
    updated_user_id = (
        await session.execute(
            text(
                "UPDATE core.users SET is_active = :active WHERE user_id = :user "
                "AND tenant_id = :tenant RETURNING user_id"
            ),
            {"active": payload.is_active, "user": user_id, "tenant": UUID(actor.tenant_id)},
        )
    ).scalar_one_or_none()
    if updated_user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    await write_audit(
        session,
        tenant_id=actor.tenant_id,
        actor_user_id=actor.user_id,
        action="user.status_change",
        object_type="user",
        object_id=str(user_id),
        after_state={"is_active": payload.is_active},
    )
    await session.commit()
    return {"user_id": str(user_id), "is_active": payload.is_active}
