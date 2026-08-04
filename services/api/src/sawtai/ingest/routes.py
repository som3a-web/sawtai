from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.auth.service import UserContext, require
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1", tags=["messages"])


class ReviewRequest(BaseModel):
    occurred_at: datetime
    node_code: str


@router.get("/messages")
async def messages(
    sentiment: str | None = None,
    dialect: str | None = None,
    topic_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: UserContext = Depends(require("message:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    clauses = ["m.tenant_id = :tenant"]
    params: dict[str, object] = {"tenant": user.tenant_id, "limit": limit}
    if sentiment:
        clauses.append("s.label::text = :sentiment")
        params["sentiment"] = sentiment
    if dialect:
        clauses.append("m.dialect::text = :dialect")
        params["dialect"] = dialect
    if topic_id:
        clauses.append("mt.topic_id = CAST(:topic_id AS uuid)")
        params["topic_id"] = topic_id
    where = " AND ".join(clauses)
    rows = (
        await session.execute(
            text(
                f"""
                SELECT m.message_id, m.occurred_at, m.raw_text, m.lang_primary::text,
                       m.dialect::text, m.dialect_conf, m.code_switch_ratio, m.engagement,
                       c.code AS channel_code, c.name_ar AS channel_name_ar,
                       s.label::text AS sentiment_label, s.score AS sentiment_score,
                       greatest(s.prob_neg, s.prob_neu, s.prob_pos) AS sentiment_confidence,
                       s.sarcasm_flag, n.code AS node_code, n.label_ar AS classification_label_ar,
                       cl.confidence AS classification_confidence, cl.is_abstained,
                       t.topic_id, t.label_ar AS topic_label_ar, mt.similarity
                FROM core.messages m
                JOIN core.channels c ON c.channel_id = m.channel_id
                LEFT JOIN core.sentiment_scores s
                  ON s.message_id = m.message_id AND s.occurred_at = m.occurred_at
                LEFT JOIN core.classifications cl
                  ON cl.message_id = m.message_id AND cl.occurred_at = m.occurred_at AND cl.rank = 1
                LEFT JOIN core.taxonomy_nodes n ON n.node_id = cl.node_id
                LEFT JOIN core.message_topics mt
                  ON mt.message_id = m.message_id AND mt.occurred_at = m.occurred_at
                LEFT JOIN core.topics t ON t.topic_id = mt.topic_id
                WHERE {where}
                ORDER BY m.occurred_at DESC LIMIT :limit
                """
            ),
            params,
        )
    ).mappings().all()
    items = []
    for row in rows:
        items.append(
            {
                "message_id": row["message_id"],
                "occurred_at": row["occurred_at"],
                "channel": {"code": row["channel_code"], "name_ar": row["channel_name_ar"]},
                "text": row["raw_text"],
                "lang_primary": row["lang_primary"],
                "dialect": row["dialect"],
                "dialect_conf": row["dialect_conf"],
                "code_switch_ratio": row["code_switch_ratio"],
                "sentiment": {
                    "label": row["sentiment_label"],
                    "score": row["sentiment_score"],
                    "confidence": row["sentiment_confidence"],
                    "sarcasm_flag": row["sarcasm_flag"],
                    "model": "marbertv2-sent",
                    "version": "2026.08.demo",
                },
                "classification": {
                    "node_code": row["node_code"],
                    "label_ar": row["classification_label_ar"],
                    "confidence": row["classification_confidence"],
                    "abstained": row["is_abstained"],
                },
                "topics": [{"topic_id": row["topic_id"], "label_ar": row["topic_label_ar"], "similarity": row["similarity"]}],
                "engagement": row["engagement"],
                "pii_redacted": [{"type": "PHONE", "count": 1}] if "<PHONE_1>" in row["raw_text"] else [],
                "flags": [],
            }
        )
    return {"items": items, "next_cursor": None, "total_estimate": len(items), "provenance": "synthetic replay corpus"}


@router.post("/sources/replay/poll")
async def replay_poll(user: UserContext = Depends(require("message:read"))) -> dict[str, object]:
    return {"status": "replay_ready", "emitted": 240, "speed": 8, "tenant_id": user.tenant_id}


@router.post("/messages/{message_id}/review")
async def review_message(
    message_id: str,
    payload: ReviewRequest,
    user: UserContext = Depends(require("message:review")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    result = await session.execute(
        text(
            """
            UPDATE core.classifications c
            SET reviewed_by = CAST(:user_id AS uuid),
                reviewed_node_id = n.node_id,
                reviewed_at = now()
            FROM core.taxonomy_nodes n
            WHERE c.tenant_id = CAST(:tenant AS uuid)
              AND c.message_id = CAST(:message_id AS uuid)
              AND c.occurred_at = :occurred_at
              AND c.rank = 1
              AND n.tenant_id = c.tenant_id
              AND n.code = :node_code
            RETURNING c.classification_id
            """
        ),
        {
            "user_id": user.user_id,
            "tenant": user.tenant_id,
            "message_id": message_id,
            "occurred_at": payload.occurred_at,
            "node_code": payload.node_code,
        },
    )
    classification_id = result.scalar_one_or_none()
    if classification_id is None:
        raise HTTPException(status_code=404, detail="Message or taxonomy node not found")
    await session.commit()
    return {"status": "reviewed", "classification_id": classification_id, "node_code": payload.node_code}
