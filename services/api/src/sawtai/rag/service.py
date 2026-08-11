"""Public retrieval and drafting facade."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.arabic import normalize_for_search

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
) -> tuple[RetrievedChunk, ...]:
    normalized = normalize_for_search(query)
    rows = (
        await session.execute(
            text(
                """
                SELECT dc.chunk_id, dc.document_id, d.title_ar, d.title_en,
                       dc.heading_path, dc.text,
                       greatest(
                           similarity(dc.norm_text, :query),
                           similarity(dc.text, :raw_query)
                       ) AS score
                FROM core.doc_chunks dc
                JOIN core.documents d ON d.document_id = dc.document_id
                WHERE dc.tenant_id = :tenant_id
                  AND d.tenant_id = :tenant_id
                  AND d.is_approved
                  AND (d.effective_from IS NULL OR d.effective_from <= CURRENT_DATE)
                  AND (d.effective_to IS NULL OR d.effective_to > CURRENT_DATE)
                ORDER BY score DESC, dc.seq
                LIMIT :limit
                """
            ),
            {
                "tenant_id": tenant_id,
                "query": normalized,
                "raw_query": query,
                "limit": max(20, limit * 4),
            },
        )
    ).mappings().all()
    candidates = tuple(
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            title_ar=row["title_ar"],
            title_en=row["title_en"],
            heading_path=row["heading_path"],
            text=row["text"],
            score=max(
                float(row["score"] or 0.0),
                lexical_overlap(query, row["text"]),
            ),
        )
        for row in rows
    )
    return tuple(sorted(candidates, key=lambda chunk: chunk.score, reverse=True)[:limit])


async def generate_grounded_reply(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    message_id: UUID,
    message_occurred_at: datetime,
    citizen_text: str,
    language: str,
    retrieval_gate: float,
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
