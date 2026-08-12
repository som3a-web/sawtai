from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.auth.service import UserContext, require
from sawtai.cases.service import (
    add_case_note,
    assign_case,
    create_case,
    escalate_case,
    get_case_detail,
    list_cases,
    transition_case,
    update_case,
)
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])
CaseStatus = Literal["new", "triaged", "assigned", "awaiting_response", "responded", "resolved", "closed", "rejected"]
Severity = Literal["low", "medium", "high", "critical"]


class CaseCreateRequest(BaseModel):
    title_ar: str = Field(min_length=3, max_length=300)
    title_en: str = Field(min_length=3, max_length=300)
    node_id: UUID | None = None
    severity: Severity = "medium"


class CaseUpdateRequest(BaseModel):
    title_ar: str | None = Field(default=None, min_length=3, max_length=300)
    title_en: str | None = Field(default=None, min_length=3, max_length=300)
    severity: Severity | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "CaseUpdateRequest":
        if self.title_ar is None and self.title_en is None and self.severity is None:
            raise ValueError("At least one field is required")
        return self


class CaseAssignmentRequest(BaseModel):
    assigned_to: UUID


class CaseStatusRequest(BaseModel):
    status: CaseStatus
    note: str | None = Field(default=None, max_length=1000)


class CaseNoteRequest(BaseModel):
    note: str = Field(min_length=2, max_length=2000)


class CaseEscalationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.get("")
async def cases(
    status_filter: CaseStatus | None = Query(default=None, alias="status"),
    severity: Severity | None = None,
    assigned_to: UUID | None = None,
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=200),
    user: UserContext = Depends(require("case:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return await list_cases(
        session,
        tenant_id=UUID(user.tenant_id),
        status_filter=status_filter,
        severity_filter=severity,
        assigned_to=assigned_to,
        search=search,
        limit=limit,
    )


@router.get("/metadata")
async def case_metadata(
    user: UserContext = Depends(require("case:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    taxonomy = (
        await session.execute(
            text(
                """
                SELECT node_id, code, label_ar, label_en, sla_hours
                FROM core.taxonomy_nodes
                WHERE tenant_id = :tenant_id AND is_active
                ORDER BY code
                """
            ),
            {"tenant_id": UUID(user.tenant_id)},
        )
    ).mappings().all()
    assignees = (
        await session.execute(
            text(
                """
                SELECT DISTINCT u.user_id, u.display_name_ar, u.display_name_en,
                       array_agg(DISTINCT r.code) AS roles
                FROM core.users u
                JOIN core.user_roles ur ON ur.user_id = u.user_id
                JOIN core.roles r ON r.role_id = ur.role_id
                WHERE u.tenant_id = :tenant_id AND u.is_active
                  AND r.permissions @> '["case:read"]'::jsonb
                GROUP BY u.user_id ORDER BY u.display_name_en
                """
            ),
            {"tenant_id": UUID(user.tenant_id)},
        )
    ).mappings().all()
    return {
        "taxonomy": [dict(row) for row in taxonomy],
        "assignees": [dict(row) for row in assignees],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def new_case(
    payload: CaseCreateRequest,
    user: UserContext = Depends(require("case:write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        case_id = await create_case(
            session,
            tenant_id=UUID(user.tenant_id),
            actor_user_id=UUID(user.user_id),
            title_ar=payload.title_ar,
            title_en=payload.title_en,
            node_id=payload.node_id,
            severity=payload.severity,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"case_id": str(case_id), "status": "created"}


@router.get("/{case_id}")
async def case_detail(
    case_id: UUID,
    user: UserContext = Depends(require("case:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        return await get_case_detail(session, tenant_id=UUID(user.tenant_id), case_id=case_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{case_id}")
async def edit_case(
    case_id: UUID,
    payload: CaseUpdateRequest,
    user: UserContext = Depends(require("case:write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await update_case(
            session,
            tenant_id=UUID(user.tenant_id), actor_user_id=UUID(user.user_id),
            case_id=case_id, title_ar=payload.title_ar,
            title_en=payload.title_en, severity=payload.severity,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"case_id": str(case_id), "status": "updated"}


@router.post("/{case_id}/assign")
async def assign(
    case_id: UUID,
    payload: CaseAssignmentRequest,
    user: UserContext = Depends(require("case:write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await assign_case(
            session,
            tenant_id=UUID(user.tenant_id), actor_user_id=UUID(user.user_id),
            case_id=case_id, assignee_user_id=payload.assigned_to,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"case_id": str(case_id), "status": "assigned"}


@router.post("/{case_id}/status")
async def change_status(
    case_id: UUID,
    payload: CaseStatusRequest,
    user: UserContext = Depends(require("case:write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await transition_case(
            session,
            tenant_id=UUID(user.tenant_id), actor_user_id=UUID(user.user_id),
            case_id=case_id, next_status=payload.status, note=payload.note,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"case_id": str(case_id), "status": payload.status}


@router.post("/{case_id}/notes")
async def add_note(
    case_id: UUID,
    payload: CaseNoteRequest,
    user: UserContext = Depends(require("case:write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await add_case_note(
            session,
            tenant_id=UUID(user.tenant_id), actor_user_id=UUID(user.user_id),
            case_id=case_id, note=payload.note,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"case_id": str(case_id), "status": "noted"}


@router.post("/{case_id}/escalate")
async def escalate(
    case_id: UUID,
    payload: CaseEscalationRequest,
    user: UserContext = Depends(require("case:write")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await escalate_case(
            session,
            tenant_id=UUID(user.tenant_id), actor_user_id=UUID(user.user_id),
            case_id=case_id, reason=payload.reason,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"case_id": str(case_id), "status": "escalated"}
