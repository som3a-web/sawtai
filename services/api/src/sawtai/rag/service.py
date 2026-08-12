"""Public retrieval and drafting facade."""

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from time import monotonic
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.arabic import normalize_for_search
from sawtai.audit.service import write_audit
from sawtai.config import Settings, get_settings
from sawtai.rag.ingestion import (
    DocumentIngestionError,
    ValidatedUpload,
    embed_texts,
    extract_document,
    get_object,
    put_object,
    rerank_texts,
    validate_upload,
    vector_literal,
)

INJECTION_PATTERNS = (
    re.compile(r"ignore (?:all |the )?(?:previous|prior|system) instructions", re.IGNORECASE),
    re.compile(r"reveal (?:the )?(?:system prompt|hidden instructions)", re.IGNORECASE),
    re.compile(r"تجاهل (?:كل |جميع )?(?:التعليمات|الأوامر)(?: السابقة)?"),
    re.compile(r"اكشف (?:تعليمات|موجه|رسالة) النظام"),
)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    title_ar: str
    title_en: str | None
    heading_path: str | None
    text: str
    score: float
    dense_score: float
    sparse_score: float
    rerank_score: float
    embedding_provider: str
    rerank_provider: str


class UploadedDocumentError(DocumentIngestionError):
    def __init__(self, document_id: UUID, code: str, message: str) -> None:
        super().__init__(code, message)
        self.document_id = document_id


@dataclass(frozen=True)
class GeneratedReply:
    response_id: UUID
    inference_run_id: UUID
    body: str
    grounding_score: float
    abstained: bool
    abstain_reason: str | None
    policy_flags: tuple[str, ...]
    citations: tuple[RetrievedChunk, ...]


class GenerationProvider(Protocol):
    name: str
    version: str

    async def generate(self, *, citizen_text: str, language: str, context: str) -> str: ...


class GroundedTemplateProvider:
    name = "grounded-template"
    version = "v1"

    async def generate(self, *, citizen_text: str, language: str, context: str) -> str:
        excerpt = context.strip().replace("\n", " ")[:380]
        if language == "en":
            return (
                "Thank you for contacting us. According to the approved service information: "
                f"“{excerpt}” If you need help with a specific request, please provide its reference number."
            )
        return (
            "نشكركم على تواصلكم معنا. وفقاً لمعلومات الخدمة المعتمدة: "
            f"«{excerpt}». إذا كنتم بحاجة إلى متابعة طلب محدد، يرجى تزويدنا برقم المرجع."
        )


def structure_chunks(content: str, default_heading: str | None = None) -> tuple[tuple[str | None, str], ...]:
    heading = default_heading
    sections: list[tuple[str | None, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        paragraph = "\n".join(buffer).strip()
        words = paragraph.split()
        for start in range(0, len(words), 180):
            text_value = " ".join(words[start : start + 180]).strip()
            if text_value:
                sections.append((heading, text_value))
        buffer.clear()

    for raw_line in content.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip() or heading
        elif not line:
            flush()
        else:
            buffer.append(line)
    flush()
    return tuple(sections)


async def list_documents(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    search: str | None = None,
) -> dict[str, object]:
    rows = (
        await session.execute(
            text(
                """
                SELECT d.document_id, d.kind::text, d.title_ar, d.title_en,
                       d.lang::text, d.version, d.effective_from, d.effective_to,
                       d.is_approved, d.approved_by, d.object_key, d.created_at,
                       (d.effective_to IS NOT NULL AND d.effective_to <= CURRENT_DATE) AS is_retired,
                       (d.is_approved
                        AND (d.effective_from IS NULL OR d.effective_from <= CURRENT_DATE)
                        AND (d.effective_to IS NULL OR d.effective_to > CURRENT_DATE)) AS is_retrievable,
                       count(DISTINCT dc.chunk_id) AS chunk_count,
                       count(DISTINCT rc.response_id) AS citation_count,
                       creator.actor_user_id AS created_by,
                       creator.display_name_ar AS creator_name_ar,
                       creator.display_name_en AS creator_name_en,
                       approver.display_name_ar AS approver_name_ar,
                       approver.display_name_en AS approver_name_en,
                       processing.action AS processing_action,
                       processing.after_state AS processing_state
                FROM core.documents d
                LEFT JOIN core.doc_chunks dc ON dc.document_id = d.document_id
                LEFT JOIN core.response_citations rc ON rc.document_id = d.document_id
                LEFT JOIN LATERAL (
                    SELECT a.actor_user_id, u.display_name_ar, u.display_name_en
                    FROM core.audit_log a
                    LEFT JOIN core.users u ON u.user_id = a.actor_user_id
                    WHERE a.tenant_id = d.tenant_id AND a.object_id = d.document_id
                      AND a.action = 'document.create'
                    ORDER BY a.occurred_at, a.audit_id LIMIT 1
                ) creator ON true
                LEFT JOIN LATERAL (
                    SELECT a.action, a.after_state
                    FROM core.audit_log a
                    WHERE a.tenant_id = d.tenant_id AND a.object_id = d.document_id
                      AND a.action IN ('document.create','document.index',
                                       'document.ingest.failed','document.reindex')
                    ORDER BY a.occurred_at DESC, a.audit_id DESC LIMIT 1
                ) processing ON true
                LEFT JOIN core.users approver ON approver.user_id = d.approved_by
                WHERE d.tenant_id = :tenant_id
                  AND (CAST(:pattern AS text) IS NULL OR d.title_ar ILIKE :pattern
                       OR COALESCE(d.title_en, '') ILIKE :pattern)
                GROUP BY d.document_id, creator.actor_user_id,
                         creator.display_name_ar, creator.display_name_en,
                         approver.display_name_ar, approver.display_name_en,
                         processing.action, processing.after_state
                ORDER BY d.created_at DESC, d.document_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "pattern": f"%{search}%" if search else None,
            },
        )
    ).mappings().all()
    items: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        processing_state = dict(item.pop("processing_state") or {})
        item["ingestion_status"] = processing_state.get(
            "ingestion_status",
            "indexed" if int(str(item["chunk_count"])) > 0 else "processing",
        )
        item["extraction_method"] = processing_state.get("extraction_method")
        item["embedding_provider"] = processing_state.get("embedding_provider")
        item["storage_backend"] = processing_state.get("storage_backend")
        item["ingestion_error"] = processing_state.get("error_message")
        items.append(item)
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "approved": sum(bool(item["is_retrievable"]) for item in items),
            "pending": sum(not bool(item["is_approved"]) and not bool(item["is_retired"]) for item in items),
            "retired": sum(bool(item["is_retired"]) for item in items),
            "chunks": sum(int(str(item["chunk_count"])) for item in items),
        },
    }


async def get_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
) -> dict[str, object]:
    document = (
        await session.execute(
            text(
                """
                SELECT d.document_id, d.kind::text, d.title_ar, d.title_en,
                       d.lang::text, d.version, d.effective_from, d.effective_to,
                       d.is_approved, d.approved_by, d.object_key,
                       encode(d.sha256, 'hex') AS sha256, d.org_unit_id, d.created_at,
                       creator.actor_user_id AS created_by,
                       creator.display_name_ar AS creator_name_ar,
                       creator.display_name_en AS creator_name_en,
                       approver.display_name_ar AS approver_name_ar,
                       approver.display_name_en AS approver_name_en,
                       processing.action AS processing_action,
                       processing.after_state AS processing_state,
                       (d.effective_to IS NOT NULL AND d.effective_to <= CURRENT_DATE) AS is_retired,
                       (d.is_approved
                        AND (d.effective_from IS NULL OR d.effective_from <= CURRENT_DATE)
                        AND (d.effective_to IS NULL OR d.effective_to > CURRENT_DATE)) AS is_retrievable
                FROM core.documents d
                LEFT JOIN LATERAL (
                    SELECT a.actor_user_id, u.display_name_ar, u.display_name_en
                    FROM core.audit_log a
                    LEFT JOIN core.users u ON u.user_id = a.actor_user_id
                    WHERE a.tenant_id = d.tenant_id AND a.object_id = d.document_id
                      AND a.action = 'document.create'
                    ORDER BY a.occurred_at, a.audit_id LIMIT 1
                ) creator ON true
                LEFT JOIN LATERAL (
                    SELECT a.action, a.after_state
                    FROM core.audit_log a
                    WHERE a.tenant_id = d.tenant_id AND a.object_id = d.document_id
                      AND a.action IN ('document.create','document.index',
                                       'document.ingest.failed','document.reindex')
                    ORDER BY a.occurred_at DESC, a.audit_id DESC LIMIT 1
                ) processing ON true
                LEFT JOIN core.users approver ON approver.user_id = d.approved_by
                WHERE d.tenant_id = :tenant_id AND d.document_id = :document_id
                """
            ),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
    ).mappings().one_or_none()
    if document is None:
        raise LookupError("Document not found")
    chunks = (
        await session.execute(
            text(
                """
                SELECT chunk_id, seq, heading_path, text, token_count, lang::text
                FROM core.doc_chunks
                WHERE tenant_id = :tenant_id AND document_id = :document_id
                ORDER BY seq
                """
            ),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
    ).mappings().all()
    history = (
        await session.execute(
            text(
                """
                SELECT a.audit_id, a.occurred_at, a.action, a.outcome,
                       a.before_state, a.after_state,
                       u.display_name_ar AS actor_name_ar,
                       u.display_name_en AS actor_name_en
                FROM core.audit_log a
                LEFT JOIN core.users u ON u.user_id = a.actor_user_id
                WHERE a.tenant_id = :tenant_id AND a.object_type = 'document'
                  AND a.object_id = :document_id
                ORDER BY a.occurred_at DESC, a.audit_id DESC
                """
            ),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
    ).mappings().all()
    item = dict(document)
    processing_state = dict(item.pop("processing_state") or {})
    item["ingestion_status"] = processing_state.get(
        "ingestion_status",
        "indexed" if chunks else "processing",
    )
    item["extraction_method"] = processing_state.get("extraction_method")
    item["embedding_provider"] = processing_state.get("embedding_provider")
    item["storage_backend"] = processing_state.get("storage_backend")
    item["ingestion_error"] = processing_state.get("error_message")
    return {**item, "chunks": [dict(row) for row in chunks], "history": [dict(row) for row in history]}


async def _replace_chunks(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
    language: str,
    content: str,
    heading_path: str | None,
    settings: Settings,
) -> int:
    chunks = structure_chunks(content, heading_path)
    if not chunks:
        raise ValueError("Document content must contain readable text")
    await session.execute(
        text("DELETE FROM core.doc_chunks WHERE tenant_id = :tenant_id AND document_id = :document_id"),
        {"tenant_id": tenant_id, "document_id": document_id},
    )
    embeddings = await embed_texts([chunk_text for _, chunk_text in chunks], settings)
    for sequence, ((heading, chunk_text), embedding) in enumerate(zip(chunks, embeddings.vectors, strict=True), start=1):
        normalized = normalize_for_search(chunk_text)
        await session.execute(
            text(
                """
                INSERT INTO core.doc_chunks (
                    chunk_id, tenant_id, document_id, seq, heading_path, text,
                    norm_text, token_count, lang, embedding, tsv
                ) VALUES (
                    :chunk_id, :tenant_id, :document_id, :seq, :heading_path,
                    :text, :norm_text, :token_count, CAST(:lang AS core.lang_code),
                    CAST(:embedding AS vector),
                    to_tsvector('simple', :norm_text)
                )
                """
            ),
            {
                "chunk_id": uuid4(),
                "tenant_id": tenant_id,
                "document_id": document_id,
                "seq": sequence,
                "heading_path": heading,
                "text": chunk_text,
                "norm_text": normalized,
                "token_count": len(chunk_text.split()),
                "lang": language,
                "embedding": vector_literal(embedding),
            },
        )
    return len(chunks)


async def create_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    kind: str,
    title_ar: str,
    title_en: str | None,
    language: str,
    version: str,
    effective_from: date | None,
    effective_to: date | None,
    content: str,
    heading_path: str | None,
    org_unit_id: UUID | None,
    settings: Settings | None = None,
) -> UUID:
    current_settings = settings or get_settings()
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    duplicate = (
        await session.execute(
            text(
                """
                SELECT document_id FROM core.documents
                WHERE tenant_id = :tenant_id AND sha256 = :sha256
                  AND title_ar = :title_ar AND version = :version
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "sha256": digest, "title_ar": title_ar, "version": version},
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ValueError("This document version already exists")
    document_id = uuid4()
    object_key = f"knowledge/{tenant_id}/{document_id}/{digest.hex()[:16]}.txt"
    storage = await put_object(
        current_settings,
        object_key=object_key,
        content=content.encode("utf-8"),
        media_type="text/plain",
    )
    await session.execute(
        text(
            """
            INSERT INTO core.documents (
                document_id, tenant_id, kind, title_ar, title_en, lang, version,
                effective_from, effective_to, is_approved, object_key, sha256, org_unit_id
            ) VALUES (
                :document_id, :tenant_id, CAST(:kind AS core.doc_kind), :title_ar,
                :title_en, CAST(:lang AS core.lang_code), :version,
                :effective_from, :effective_to, false, :object_key, :sha256, :org_unit_id
            )
            """
        ),
        {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "kind": kind,
            "title_ar": title_ar,
            "title_en": title_en,
            "lang": language,
            "version": version,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "object_key": object_key,
            "sha256": digest,
            "org_unit_id": org_unit_id,
        },
    )
    chunk_count = await _replace_chunks(
        session,
        tenant_id=tenant_id,
        document_id=document_id,
        language=language,
        content=content,
        heading_path=heading_path,
        settings=current_settings,
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(actor_user_id),
        action="document.create",
        object_type="document",
        object_id=str(document_id),
        after_state={
            "version": version,
            "kind": kind,
            "chunks": chunk_count,
            "approved": False,
            "ingestion_status": "indexed",
            "extraction_method": "manual_text",
            "storage_backend": storage,
        },
    )
    await session.commit()
    return document_id


async def ingest_uploaded_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    kind: str,
    title_ar: str,
    title_en: str | None,
    language: str,
    version: str,
    effective_from: date | None,
    effective_to: date | None,
    org_unit_id: UUID | None,
    filename: str,
    media_type: str | None,
    content: bytes,
    settings: Settings,
) -> dict[str, object]:
    validated = validate_upload(
        filename=filename,
        content=content,
        declared_media_type=media_type,
        max_bytes=settings.document_max_upload_bytes,
    )
    duplicate = (
        await session.execute(
            text(
                """
                SELECT document_id FROM core.documents
                WHERE tenant_id = :tenant_id AND sha256 = :sha256
                  AND title_ar = :title_ar AND version = :version
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "sha256": validated.sha256,
                "title_ar": title_ar,
                "version": version,
            },
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise DocumentIngestionError("duplicate_version", "This document version already exists")
    document_id = uuid4()
    object_key = f"knowledge/{tenant_id}/{document_id}/{validated.sha256.hex()[:16]}-{validated.filename}"
    storage = await put_object(
        settings,
        object_key=object_key,
        content=content,
        media_type=validated.media_type,
    )
    await session.execute(
        text(
            """
            INSERT INTO core.documents (
                document_id, tenant_id, kind, title_ar, title_en, lang, version,
                effective_from, effective_to, is_approved, object_key, sha256, org_unit_id
            ) VALUES (
                :document_id, :tenant_id, CAST(:kind AS core.doc_kind), :title_ar,
                :title_en, CAST(:lang AS core.lang_code), :version,
                :effective_from, :effective_to, false, :object_key, :sha256, :org_unit_id
            )
            """
        ),
        {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "kind": kind,
            "title_ar": title_ar,
            "title_en": title_en,
            "lang": language,
            "version": version,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "object_key": object_key,
            "sha256": validated.sha256,
            "org_unit_id": org_unit_id,
        },
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(actor_user_id),
        action="document.create",
        object_type="document",
        object_id=str(document_id),
        after_state={
            "version": version,
            "kind": kind,
            "approved": False,
            "ingestion_status": "processing",
            "filename": validated.filename,
            "media_type": validated.media_type,
            "file_size": len(content),
            "storage_backend": storage,
        },
    )
    await session.commit()
    return await _process_uploaded_content(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        document_id=document_id,
        language=language,
        content=content,
        validated=validated,
        settings=settings,
        storage=storage,
    )


async def _process_uploaded_content(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    document_id: UUID,
    language: str,
    content: bytes,
    validated: ValidatedUpload,
    settings: Settings,
    storage: str,
) -> dict[str, object]:
    try:
        extraction = await asyncio.to_thread(
            extract_document,
            content=content,
            validated=validated,
            max_pages=settings.document_max_pages,
        )
        chunk_count = await _replace_chunks(
            session,
            tenant_id=tenant_id,
            document_id=document_id,
            language=language,
            content=extraction.text,
            heading_path=None,
            settings=settings,
        )
        embedding_provider = (await embed_texts([extraction.text[:4000]], settings)).provider
        await write_audit(
            session,
            tenant_id=str(tenant_id),
            actor_user_id=str(actor_user_id),
            action="document.index",
            object_type="document",
            object_id=str(document_id),
            after_state={
                "ingestion_status": "indexed",
                "chunks": chunk_count,
                "extraction_method": extraction.method,
                "page_count": extraction.page_count,
                "warnings": extraction.warnings,
                "embedding_provider": embedding_provider,
                "storage_backend": storage,
            },
        )
        await session.commit()
        return {
            "document_id": str(document_id),
            "status": "pending_approval",
            "ingestion_status": "indexed",
            "chunks": chunk_count,
            "extraction_method": extraction.method,
            "page_count": extraction.page_count,
            "warnings": extraction.warnings,
            "embedding_provider": embedding_provider,
            "storage_backend": storage,
        }
    except DocumentIngestionError as error:
        await session.rollback()
        await _record_ingestion_failure(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            document_id=document_id,
            error=error,
        )
        raise UploadedDocumentError(document_id, error.code, str(error)) from error


async def _record_ingestion_failure(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    document_id: UUID,
    error: DocumentIngestionError,
) -> None:
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(actor_user_id),
        action="document.ingest.failed",
        object_type="document",
        object_id=str(document_id),
        outcome="failure",
        after_state={
            "ingestion_status": "failed",
            "error_code": error.code,
            "error_message": str(error),
        },
    )
    await session.commit()


async def retry_document_ingestion(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
    actor_user_id: UUID,
    settings: Settings,
) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT d.object_key, d.lang::text, d.is_approved,
                       count(rc.response_id) AS citation_count
                FROM core.documents d
                LEFT JOIN core.response_citations rc ON rc.document_id = d.document_id
                WHERE d.tenant_id = :tenant_id AND d.document_id = :document_id
                GROUP BY d.document_id
                """
            ),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Document not found")
    if row["is_approved"] or int(row["citation_count"]) > 0:
        raise ValueError("Approved or cited documents cannot be reprocessed")
    content = await get_object(settings, object_key=str(row["object_key"]))
    filename = str(row["object_key"]).rsplit("/", 1)[-1].split("-", 1)[-1]
    validated = validate_upload(
        filename=filename,
        content=content,
        declared_media_type=None,
        max_bytes=settings.document_max_upload_bytes,
    )
    return await _process_uploaded_content(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        document_id=document_id,
        language=str(row["lang"]),
        content=content,
        validated=validated,
        settings=settings,
        storage="s3-compatible" if settings.object_store_endpoint else "local-prototype",
    )


async def approve_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
    approver_user_id: UUID,
) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT d.is_approved, d.effective_to, creator.actor_user_id AS created_by,
                       (SELECT count(*) FROM core.doc_chunks dc
                        WHERE dc.document_id = d.document_id) AS chunk_count
                FROM core.documents d
                LEFT JOIN LATERAL (
                    SELECT actor_user_id FROM core.audit_log
                    WHERE tenant_id = d.tenant_id AND object_id = d.document_id
                      AND action = 'document.create'
                    ORDER BY occurred_at, audit_id LIMIT 1
                ) creator ON true
                WHERE d.tenant_id = :tenant_id AND d.document_id = :document_id
                FOR UPDATE OF d
                """
            ),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Document not found")
    if row["is_approved"]:
        raise ValueError("Document is already approved")
    if int(row["chunk_count"]) == 0:
        raise ValueError("Document processing must succeed before approval")
    if row["effective_to"] is not None and row["effective_to"] <= date.today():
        raise ValueError("A retired or expired document cannot be approved")
    if row["created_by"] == approver_user_id:
        raise PermissionError("Document creators cannot approve their own source")
    await session.execute(
        text(
            """
            UPDATE core.documents SET is_approved = true, approved_by = :approver
            WHERE tenant_id = :tenant_id AND document_id = :document_id
            """
        ),
        {"tenant_id": tenant_id, "document_id": document_id, "approver": approver_user_id},
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(approver_user_id),
        action="document.approve",
        object_type="document",
        object_id=str(document_id),
        before_state={"approved": False},
        after_state={"approved": True},
    )
    await session.commit()


async def retire_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
    actor_user_id: UUID,
) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT is_approved, effective_to FROM core.documents
                WHERE tenant_id = :tenant_id AND document_id = :document_id
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise LookupError("Document not found")
    if row["effective_to"] is not None and row["effective_to"] <= date.today():
        raise ValueError("Document is already retired")
    await session.execute(
        text(
            """
            UPDATE core.documents
            SET is_approved = false, effective_to = CURRENT_DATE
            WHERE tenant_id = :tenant_id AND document_id = :document_id
            """
        ),
        {"tenant_id": tenant_id, "document_id": document_id},
    )
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(actor_user_id),
        action="document.retire",
        object_type="document",
        object_id=str(document_id),
        before_state={"approved": bool(row["is_approved"])},
        after_state={"approved": False, "effective_to": date.today().isoformat()},
    )
    await session.commit()


async def reindex_document(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    document_id: UUID,
    actor_user_id: UUID,
    settings: Settings | None = None,
) -> int:
    current_settings = settings or get_settings()
    rows = (
        await session.execute(
            text(
                """
                SELECT dc.chunk_id, dc.text
                FROM core.documents d
                JOIN core.doc_chunks dc ON dc.document_id = d.document_id
                WHERE d.tenant_id = :tenant_id AND d.document_id = :document_id
                ORDER BY dc.seq
                """
            ),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
    ).mappings().all()
    exists = (
        await session.execute(
            text("SELECT 1 FROM core.documents WHERE tenant_id = :tenant_id AND document_id = :document_id"),
            {"tenant_id": tenant_id, "document_id": document_id},
        )
    ).scalar_one_or_none()
    if exists is None:
        raise LookupError("Document not found")
    if not rows:
        raise ValueError("Document has no indexed content")
    embeddings = await embed_texts([str(row["text"]) for row in rows], current_settings)
    for row, embedding in zip(rows, embeddings.vectors, strict=True):
        normalized = normalize_for_search(str(row["text"]))
        await session.execute(
            text(
                """
                UPDATE core.doc_chunks
                SET norm_text = :norm_text, token_count = :token_count,
                    tsv = to_tsvector('simple', :norm_text),
                    embedding = CAST(:embedding AS vector)
                WHERE tenant_id = :tenant_id AND chunk_id = :chunk_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "chunk_id": row["chunk_id"],
                "norm_text": normalized,
                "token_count": len(str(row["text"]).split()),
                "embedding": vector_literal(embedding),
            },
        )
    chunk_count = len(rows)
    await write_audit(
        session,
        tenant_id=str(tenant_id),
        actor_user_id=str(actor_user_id),
        action="document.reindex",
        object_type="document",
        object_id=str(document_id),
        after_state={
            "chunks": chunk_count,
            "ingestion_status": "indexed",
            "embedding_provider": embeddings.provider,
        },
    )
    await session.commit()
    return chunk_count


def has_prompt_injection(value: str) -> bool:
    return any(pattern.search(value) for pattern in INJECTION_PATTERNS)


def lexical_overlap(query: str, document: str) -> float:
    query_terms = {
        term
        for term in normalize_for_search(query).split()
        if len(term) > 2 and not term.startswith("<")
    }
    if not query_terms:
        return 0.0
    document_terms = set(normalize_for_search(document).split())
    return len(query_terms & document_terms) / len(query_terms)


async def retrieve_approved_chunks(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    query: str,
    limit: int = 5,
    settings: Settings | None = None,
) -> tuple[RetrievedChunk, ...]:
    current_settings = settings or get_settings()
    normalized = normalize_for_search(query)
    query_embeddings = await embed_texts([query], current_settings)
    query_embedding = vector_literal(query_embeddings.vectors[0])
    rows = (
        await session.execute(
            text(
                """
                WITH scored AS (
                    SELECT dc.chunk_id, dc.document_id, d.title_ar, d.title_en,
                           dc.heading_path, dc.text, dc.seq,
                           greatest(
                               similarity(dc.norm_text, :query),
                               similarity(dc.text, :raw_query)
                           ) AS sparse_score,
                           CASE
                               WHEN dc.embedding = array_fill(0.0::real, ARRAY[1024])::vector THEN 0.0
                               ELSE greatest(0.0, 1.0 - (dc.embedding <=> CAST(:embedding AS vector)))
                           END AS dense_score
                    FROM core.doc_chunks dc
                    JOIN core.documents d ON d.document_id = dc.document_id
                    WHERE dc.tenant_id = :tenant_id
                      AND d.tenant_id = :tenant_id
                      AND d.is_approved
                      AND (d.effective_from IS NULL OR d.effective_from <= CURRENT_DATE)
                      AND (d.effective_to IS NULL OR d.effective_to > CURRENT_DATE)
                )
                SELECT *, (dense_score * 0.55 + sparse_score * 0.45) AS hybrid_score
                FROM scored
                ORDER BY hybrid_score DESC, seq
                LIMIT :limit
                """
            ),
            {
                "tenant_id": tenant_id,
                "query": normalized,
                "raw_query": query,
                "embedding": query_embedding,
                "limit": max(20, limit * 4),
            },
        )
    ).mappings().all()
    remote_ranking = await rerank_texts(query, [str(row["text"]) for row in rows], current_settings)
    candidates: tuple[RetrievedChunk, ...] = tuple(
        _retrieved_chunk(
            dict(row),
            query=query,
            embedding_provider=query_embeddings.provider,
            remote_score=remote_ranking[0][index] if remote_ranking else None,
            rerank_provider=remote_ranking[1] if remote_ranking else "lexical-overlap-v1",
        )
        for index, row in enumerate(rows)
    )
    return tuple(sorted(candidates, key=lambda chunk: chunk.score, reverse=True)[:limit])


def _retrieved_chunk(
    row: Mapping[str, Any],
    *,
    query: str,
    embedding_provider: str,
    remote_score: float | None,
    rerank_provider: str,
) -> RetrievedChunk:
    values = row
    dense_score = max(0.0, float(values["dense_score"] or 0.0))
    sparse_score = max(0.0, float(values["sparse_score"] or 0.0))
    hybrid_score = max(0.0, float(values["hybrid_score"] or 0.0))
    lexical_score = lexical_overlap(query, str(values["text"]))
    if remote_score is None:
        rerank_score = lexical_score
        final_score = max(hybrid_score, lexical_score)
    else:
        rerank_score = 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, remote_score))))
        final_score = rerank_score * 0.65 + hybrid_score * 0.35
    return RetrievedChunk(
        chunk_id=values["chunk_id"],
        document_id=values["document_id"],
        title_ar=str(values["title_ar"]),
        title_en=str(values["title_en"]) if values["title_en"] else None,
        heading_path=str(values["heading_path"]) if values["heading_path"] else None,
        text=str(values["text"]),
        score=min(1.0, final_score),
        dense_score=min(1.0, dense_score),
        sparse_score=min(1.0, sparse_score),
        rerank_score=min(1.0, rerank_score),
        embedding_provider=embedding_provider,
        rerank_provider=rerank_provider,
    )


async def generate_grounded_reply(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    message_id: UUID,
    message_occurred_at: datetime,
    citizen_text: str,
    language: str,
    retrieval_gate: float,
    settings: Settings | None = None,
    provider: GenerationProvider | None = None,
) -> GeneratedReply:
    started = monotonic()
    generator = provider or GroundedTemplateProvider()
    inference_run_id = uuid4()
    retrieval_run_id = uuid4()
    response_id = uuid4()
    chunks = await retrieve_approved_chunks(
        session,
        tenant_id=tenant_id,
        query=citizen_text,
        settings=settings,
    )
    flags: list[str] = []
    reason: str | None = None
    if has_prompt_injection(citizen_text):
        flags.append("prompt_injection")
        reason = "prompt_injection_detected"
    elif not chunks or chunks[0].score < retrieval_gate:
        reason = "no_supporting_source"

    abstained = reason is not None
    body = ""
    citations: tuple[RetrievedChunk, ...] = ()
    grounding_score = 0.0
    if not abstained:
        citations = (chunks[0],)
        body = await generator.generate(
            citizen_text=citizen_text,
            language=language,
            context=chunks[0].text,
        )
        grounding_score = min(0.99, max(0.6, chunks[0].score + 0.55))

    await session.execute(
        text(
            """
            INSERT INTO core.ai_inference_log (
                inference_run_id, tenant_id, task, model_name, model_version,
                prompt_version, provider, input_ref, latency_ms, status, error_code
            ) VALUES (
                :inference_run_id, :tenant_id, 'whatsapp_reply', :model_name,
                :model_version, 'whatsapp-grounded-v1', :provider,
                CAST(:input_ref AS jsonb), :latency_ms, :status, :error_code
            )
            """
        ),
        {
            "inference_run_id": inference_run_id,
            "tenant_id": tenant_id,
            "model_name": generator.name,
            "model_version": generator.version,
            "provider": "local",
            "input_ref": json.dumps(
                {
                    "message_id": str(message_id),
                    "occurred_at": message_occurred_at.isoformat(),
                }
            ),
            "latency_ms": int((monotonic() - started) * 1000),
            "status": "abstained" if abstained else "ok",
            "error_code": reason,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO core.responses (
                response_id, tenant_id, kind, lang, audience, body, status,
                generated_by_model, model_version, prompt_version,
                inference_run_id, retrieval_run_id, grounding_score,
                unsupported_claims, policy_flags, abstained, abstain_reason
            ) VALUES (
                :response_id, :tenant_id, 'reply', CAST(:lang AS core.lang_code),
                'citizen', :body, 'draft', :model_name, :model_version,
                'whatsapp-grounded-v1', :inference_run_id, :retrieval_run_id,
                :grounding_score, '[]', CAST(:policy_flags AS jsonb),
                :abstained, :abstain_reason
            )
            """
        ),
        {
            "response_id": response_id,
            "tenant_id": tenant_id,
            "lang": language if language in {"ar", "en", "mixed"} else "ar",
            "body": body,
            "model_name": generator.name,
            "model_version": generator.version,
            "inference_run_id": inference_run_id,
            "retrieval_run_id": retrieval_run_id,
            "grounding_score": grounding_score,
            "policy_flags": json.dumps(flags),
            "abstained": abstained,
            "abstain_reason": reason,
        },
    )
    if citations:
        citation = citations[0]
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
    return GeneratedReply(
        response_id=response_id,
        inference_run_id=inference_run_id,
        body=body,
        grounding_score=grounding_score,
        abstained=abstained,
        abstain_reason=reason,
        policy_flags=tuple(flags),
        citations=citations,
    )
