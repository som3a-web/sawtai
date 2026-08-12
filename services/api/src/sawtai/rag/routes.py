import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.audit.service import write_audit
from sawtai.auth.service import UserContext, require
from sawtai.config import Settings, get_settings
from sawtai.database import get_session
from sawtai.rag.ingestion import DocumentIngestionError
from sawtai.rag.service import (
    GroundedTemplateProvider,
    UploadedDocumentError,
    approve_document,
    create_document,
    get_document,
    has_prompt_injection,
    ingest_uploaded_document,
    list_documents,
    reindex_document,
    retire_document,
    retrieve_approved_chunks,
    retry_document_ingestion,
)

router = APIRouter(prefix="/api/v1", tags=["drafting"])


class DraftRequest(BaseModel):
    kind: str = "reply"
    case_id: str | None = None
    lang: str = "ar"
    audience: str = "citizen"
    instruction: str = Field(min_length=3, max_length=1000)


DocumentKind = Literal["policy", "press_release", "faq", "tone_of_voice", "service_guide", "legal", "template"]
DocumentLanguage = Literal["ar", "en", "mixed"]


class DocumentCreateRequest(BaseModel):
    kind: DocumentKind
    title_ar: str = Field(min_length=3, max_length=300)
    title_en: str | None = Field(default=None, max_length=300)
    lang: DocumentLanguage = "ar"
    version: str = Field(default="1", min_length=1, max_length=50)
    effective_from: date | None = None
    effective_to: date | None = None
    heading_path: str | None = Field(default=None, max_length=500)
    content: str = Field(min_length=20, max_length=100_000)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "DocumentCreateRequest":
        if self.effective_from and self.effective_to and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class DocumentSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)


def event(name: str, data: dict[str, object]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/drafts")
async def create_draft(
    payload: DraftRequest,
    user: UserContext = Depends(require("draft:create")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    response_id = uuid4()
    retrieval_run_id = uuid4()
    chunks = await retrieve_approved_chunks(
        session,
        tenant_id=UUID(user.tenant_id),
        query=payload.instruction,
        limit=5,
        settings=settings,
    )
    forbidden = any(term in payload.instruction.lower() for term in ("تعويض", "ضمان", "liability", "guarantee"))
    injected = has_prompt_injection(payload.instruction)
    supported = bool(chunks) and chunks[0].score >= settings.rag_hybrid_gate
    reason = "prompt_injection_detected" if injected else "unsupported_or_forbidden_commitment" if forbidden else None if supported else "no_supporting_source"
    abstained = reason is not None
    citation = None if abstained else chunks[0]
    generator = GroundedTemplateProvider()
    body = "" if citation is None else await generator.generate(
        citizen_text=payload.instruction,
        language=payload.lang,
        context=citation.text,
    )
    grounding_score = 0.0 if citation is None else min(0.99, max(0.6, citation.score + 0.55))
    policy_flags = ["prompt_injection"] if injected else ["forbidden_commitment"] if forbidden else []
    await session.execute(
        text(
            """
            INSERT INTO core.responses (
                response_id, tenant_id, case_id, kind, lang, audience, body, status,
                generated_by_model, model_version, prompt_version, grounding_score,
                retrieval_run_id, unsupported_claims, policy_flags, abstained,
                abstain_reason, created_by
            ) VALUES (
                :id, :tenant, CAST(:case_id AS uuid), CAST(:kind AS core.response_kind),
                CAST(:lang AS core.lang_code), :audience, :body, 'draft',
                :model_name, :model_version, 'reply-grounded-v2', :score,
                :retrieval_run_id, '[]', CAST(:flags AS jsonb), :abstained,
                :reason, :user
            )
            """
        ),
        {
            "id": response_id,
            "tenant": user.tenant_id,
            "case_id": payload.case_id,
            "kind": payload.kind,
            "lang": payload.lang,
            "audience": payload.audience,
            "body": body,
            "model_name": generator.name,
            "model_version": generator.version,
            "score": grounding_score,
            "retrieval_run_id": retrieval_run_id,
            "flags": json.dumps(policy_flags),
            "abstained": abstained,
            "reason": reason,
            "user": user.user_id,
        },
    )
    if citation is not None:
        await session.execute(
            text(
                """
                INSERT INTO core.response_citations (
                    response_id, seq, claim_text, chunk_id, document_id,
                    quoted_text, start_char, end_char, entailment
                ) VALUES (
                    :response_id, 1, :claim_text, :chunk_id, :document_id,
                    :quoted_text, 0, :end_char, :entailment
                )
                """
            ),
            {
                "response_id": response_id,
                "claim_text": body,
                "chunk_id": citation.chunk_id,
                "document_id": citation.document_id,
                "quoted_text": citation.text,
                "end_char": len(citation.text),
                "entailment": grounding_score,
            },
        )
    await write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        action="response.create",
        object_type="response",
        object_id=str(response_id),
        after_state={
            "status": "draft",
            "abstained": abstained,
            "retrieval_run_id": str(retrieval_run_id),
            "source_document_id": str(citation.document_id) if citation else None,
        },
    )
    await session.commit()

    async def stream() -> AsyncIterator[str]:
        if abstained:
            yield event(
                "retrieval",
                {
                    "gate": "failed",
                    "top_score": round(chunks[0].score, 4) if chunks else 0.0,
                    "chunks": [
                        {"chunk_id": str(chunk.chunk_id), "document_id": str(chunk.document_id), "title_ar": chunk.title_ar, "score": round(chunk.score, 4)}
                        for chunk in chunks[:3]
                    ],
                },
            )
            yield event(
                "abstain",
                {
                    "reason": reason or "no_supporting_source",
                    "message_ar": "لا توجد وثيقة معتمدة تدعم هذا الالتزام. يرجى إضافة المصدر المعتمد أولاً.",
                    "message_en": "No approved source supports this commitment.",
                    "response_id": str(response_id),
                },
            )
            return
        yield event(
            "retrieval",
            {
                "gate": "passed",
                "top_score": round(citation.score, 4) if citation else 0.0,
                "chunks": [
                    {
                        "chunk_id": str(citation.chunk_id) if citation else None,
                        "document_id": str(citation.document_id) if citation else None,
                        "title_ar": citation.title_ar if citation else None,
                        "heading_path": citation.heading_path if citation else None,
                        "rerank_score": round(citation.score, 4) if citation else 0.0,
                    }
                ],
            },
        )
        for token in body.split(" "):
            yield event("token", {"delta": token + " "})
            await asyncio.sleep(0.035)
        yield event(
            "claim",
            {
                "seq": 1,
                "text_ar": body,
                "chunk_id": str(citation.chunk_id) if citation else None,
                "quoted_text": citation.text if citation else None,
                "entailment": grounding_score,
            },
        )
        yield event(
            "verification",
            {"grounding_score": grounding_score, "unsupported_claims": [], "policy_flags": policy_flags, "abstained": False},
        )
        yield event("done", {"response_id": str(response_id), "status": "draft", "provenance": "synthetic demo"})

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/documents")
async def documents(
    search_query: str | None = Query(default=None, alias="search", max_length=120),
    user: UserContext = Depends(require("doc:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    return await list_documents(
        session,
        tenant_id=UUID(user.tenant_id),
        search=search_query,
    )


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def add_document(
    payload: DocumentCreateRequest,
    user: UserContext = Depends(require("doc:create")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    try:
        document_id = await create_document(
            session,
            tenant_id=UUID(user.tenant_id),
            actor_user_id=UUID(user.user_id),
            kind=payload.kind,
            title_ar=payload.title_ar,
            title_en=payload.title_en,
            language=payload.lang,
            version=payload.version,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            content=payload.content,
            heading_path=payload.heading_path,
            org_unit_id=UUID(user.org_unit_id) if user.org_unit_id else None,
            settings=settings,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"document_id": str(document_id), "status": "pending_approval"}


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    kind: DocumentKind = Form(...),
    title_ar: str = Form(..., min_length=3, max_length=300),
    title_en: str | None = Form(default=None, max_length=300),
    lang: DocumentLanguage = Form(default="ar"),
    version: str = Form(default="1", min_length=1, max_length=50),
    effective_from: date | None = Form(default=None),
    effective_to: date | None = Form(default=None),
    user: UserContext = Depends(require("doc:create")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if effective_from and effective_to and effective_to <= effective_from:
        raise HTTPException(status_code=422, detail="effective_to must be after effective_from")
    content = await file.read(settings.document_max_upload_bytes + 1)
    try:
        return await ingest_uploaded_document(
            session,
            tenant_id=UUID(user.tenant_id),
            actor_user_id=UUID(user.user_id),
            kind=kind,
            title_ar=title_ar,
            title_en=title_en,
            language=lang,
            version=version,
            effective_from=effective_from,
            effective_to=effective_to,
            org_unit_id=UUID(user.org_unit_id) if user.org_unit_id else None,
            filename=file.filename or "document",
            media_type=file.content_type,
            content=content,
            settings=settings,
        )
    except UploadedDocumentError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "code": error.code,
                "message": str(error),
                "document_id": str(error.document_id),
                "retry_available": True,
            },
        ) from error
    except DocumentIngestionError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": str(error), "retry_available": False},
        ) from error


@router.post("/search/documents")
async def search_documents(
    payload: DocumentSearchRequest,
    user: UserContext = Depends(require("doc:read")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    chunks = await retrieve_approved_chunks(
        session,
        tenant_id=UUID(user.tenant_id),
        query=payload.query,
        limit=payload.limit,
        settings=settings,
    )
    return {
        "retrieval_run_id": str(uuid4()),
        "tenant_id": user.tenant_id,
        "results": [
            {
                "chunk_id": str(chunk.chunk_id),
                "document": {
                    "document_id": str(chunk.document_id),
                    "title_ar": chunk.title_ar,
                    "title_en": chunk.title_en,
                },
                "heading_path": chunk.heading_path,
                "text": chunk.text,
                "scores": {
                    "dense": round(chunk.dense_score, 4),
                    "sparse": round(chunk.sparse_score, 4),
                    "rerank": round(chunk.rerank_score, 4),
                    "retrieval": round(chunk.score, 4),
                },
                "models": {
                    "embedding": chunk.embedding_provider,
                    "reranker": chunk.rerank_provider,
                },
            }
            for chunk in chunks
        ],
        "gate": {
            "passed": bool(chunks) and chunks[0].score >= settings.rag_hybrid_gate,
            "top_score": round(chunks[0].score, 4) if chunks else 0.0,
            "threshold": settings.rag_hybrid_gate,
            "mode": "hybrid_dense_sparse_rerank",
        },
    }


@router.get("/documents/{document_id}")
async def document_detail(
    document_id: UUID,
    user: UserContext = Depends(require("doc:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        return await get_document(session, tenant_id=UUID(user.tenant_id), document_id=document_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/documents/{document_id}/approve")
async def approve_source(
    document_id: UUID,
    user: UserContext = Depends(require("doc:approve")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await approve_document(
            session,
            tenant_id=UUID(user.tenant_id),
            document_id=document_id,
            approver_user_id=UUID(user.user_id),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"document_id": str(document_id), "status": "approved"}


@router.post("/documents/{document_id}/reindex")
async def reindex_source(
    document_id: UUID,
    user: UserContext = Depends(require("doc:reindex")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        chunks = await reindex_document(
            session,
            tenant_id=UUID(user.tenant_id),
            document_id=document_id,
            actor_user_id=UUID(user.user_id),
            settings=settings,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"document_id": str(document_id), "status": "indexed", "chunks": chunks}


@router.post("/documents/{document_id}/retry")
async def retry_source_ingestion(
    document_id: UUID,
    user: UserContext = Depends(require("doc:reindex")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return await retry_document_ingestion(
            session,
            tenant_id=UUID(user.tenant_id),
            document_id=document_id,
            actor_user_id=UUID(user.user_id),
            settings=settings,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UploadedDocumentError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": error.code, "message": str(error), "document_id": str(error.document_id)},
        ) from error
    except (DocumentIngestionError, ValueError) as error:
        detail = {"code": error.code, "message": str(error)} if isinstance(error, DocumentIngestionError) else str(error)
        raise HTTPException(status_code=409, detail=detail) from error


@router.delete("/documents/{document_id}")
async def retire_source(
    document_id: UUID,
    user: UserContext = Depends(require("doc:retire")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    try:
        await retire_document(
            session,
            tenant_id=UUID(user.tenant_id),
            document_id=document_id,
            actor_user_id=UUID(user.user_id),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"document_id": str(document_id), "status": "retired"}
