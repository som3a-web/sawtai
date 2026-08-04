import asyncio
import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.audit.service import write_audit
from sawtai.auth.service import UserContext, require
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1", tags=["drafting"])


class DraftRequest(BaseModel):
    kind: str = "reply"
    case_id: str | None = None
    lang: str = "ar"
    audience: str = "citizen"
    instruction: str = Field(min_length=3, max_length=1000)


def event(name: str, data: dict[str, object]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/drafts")
async def create_draft(
    payload: DraftRequest,
    user: UserContext = Depends(require("draft:create")),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    response_id = uuid4()
    unsupported = any(term in payload.instruction.lower() for term in ("تعويض", "ضمان", "liability", "guarantee"))
    body = (
        ""
        if unsupported
        else "نشكركم على تواصلكم معنا. نعتذر عن الإزعاج الناتج عن تأخر جمع النفايات. "
        "وفقاً لجدول الخدمة المعتمد، تم توجيه الفريق المختص لمعالجة التراكم، "
        "وسنواصل متابعة الحالة حتى اكتمال المعالجة."
    )
    await session.execute(
        text(
            """
            INSERT INTO core.responses (
                response_id, tenant_id, case_id, kind, lang, audience, body, status,
                generated_by_model, model_version, prompt_version, grounding_score,
                unsupported_claims, policy_flags, abstained, abstain_reason, created_by
            ) VALUES (
                :id, :tenant, CAST(:case_id AS uuid), CAST(:kind AS core.response_kind),
                CAST(:lang AS core.lang_code), :audience, :body, 'draft',
                'demo-grounded-generator', 'v1', 'reply-ar-v1', :score,
                '[]', CAST(:flags AS jsonb), :abstained, :reason, :user
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
            "score": 0.0 if unsupported else 0.94,
            "flags": '["forbidden_commitment"]' if unsupported else "[]",
            "abstained": unsupported,
            "reason": "unsupported_or_forbidden_commitment" if unsupported else None,
            "user": user.user_id,
        },
    )
    await write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        action="response.create",
        object_type="response",
        object_id=str(response_id),
        after_state={"status": "draft", "abstained": unsupported},
    )
    await session.commit()

    async def stream() -> AsyncIterator[str]:
        if unsupported:
            yield event(
                "retrieval",
                {"gate": "failed", "top_score": 0.19, "chunks": []},
            )
            yield event(
                "abstain",
                {
                    "reason": "unsupported_or_forbidden_commitment",
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
                "top_score": 0.81,
                "chunks": [
                    {
                        "chunk_id": "policy-waste-collection-3",
                        "document_id": "waste-policy-v3",
                        "title_ar": "سياسة إدارة النفايات",
                        "heading_path": "الجمع > الجدول الزمني",
                        "rerank_score": 0.81,
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
                "text_ar": "تم توجيه الفريق المختص لمعالجة التراكم",
                "chunk_id": "policy-waste-collection-3",
                "quoted_text": "توجّه فرق الجمع لمعالجة التراكم وفق جدول الخدمة المعتمد",
                "entailment": 0.91,
            },
        )
        yield event(
            "verification",
            {"grounding_score": 0.94, "unsupported_claims": [], "policy_flags": [], "abstained": False},
        )
        yield event("done", {"response_id": str(response_id), "status": "draft", "provenance": "synthetic demo"})

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/search/documents")
async def search_documents(
    user: UserContext = Depends(require("draft:create")),
) -> dict[str, object]:
    return {
        "retrieval_run_id": str(uuid4()),
        "tenant_id": user.tenant_id,
        "results": [
            {
                "chunk_id": "policy-waste-collection-3",
                "document": {"document_id": "waste-policy-v3", "title_ar": "سياسة إدارة النفايات", "version": "3"},
                "heading_path": "الجمع > الجدول الزمني",
                "text": "توجّه فرق الجمع لمعالجة التراكم وفق جدول الخدمة المعتمد.",
                "scores": {"dense": 0.71, "sparse": 0.44, "rrf": 0.031, "rerank": 0.81},
            }
        ],
        "timings_ms": {"dense": 14, "sparse": 9, "fusion": 1, "rerank": 178, "total": 204},
    }
