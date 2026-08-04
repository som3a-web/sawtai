from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.auth.service import UserContext, require
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/overview")
async def overview(
    user: UserContext = Depends(require("analytics:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    tenant_id = user.tenant_id
    totals = (
        await session.execute(
            text(
                """
                SELECT count(*) AS total,
                       min(occurred_at) AS from_at,
                       max(occurred_at) AS to_at
                FROM core.messages WHERE tenant_id = :tenant
                """
            ),
            {"tenant": tenant_id},
        )
    ).mappings().one()
    sentiment = (
        await session.execute(
            text(
                """
                SELECT
                    avg(score) AS mean_score,
                    count(*) FILTER (WHERE label = 'negative')::float / nullif(count(*), 0) AS negative,
                    count(*) FILTER (WHERE label = 'neutral')::float / nullif(count(*), 0) AS neutral,
                    count(*) FILTER (WHERE label = 'positive')::float / nullif(count(*), 0) AS positive,
                    count(*) FILTER (WHERE is_abstained)::float / nullif(count(*), 0) AS abstained
                FROM core.sentiment_scores WHERE tenant_id = :tenant
                """
            ),
            {"tenant": tenant_id},
        )
    ).mappings().one()
    cases = (
        await session.execute(
            text(
                """
                SELECT count(*) FILTER (WHERE status NOT IN ('closed','resolved','rejected')) AS open_cases,
                       count(*) FILTER (WHERE sla_due_at < now() AND status NOT IN ('closed','resolved','rejected'))::float
                           / nullif(count(*) FILTER (WHERE status NOT IN ('closed','resolved','rejected')), 0) AS breach_rate
                FROM core.cases WHERE tenant_id = :tenant
                """
            ),
            {"tenant": tenant_id},
        )
    ).mappings().one()
    alert_counts = (
        await session.execute(
            text(
                """
                SELECT tier::text, count(*) AS count FROM core.alerts
                WHERE tenant_id = :tenant AND status IN ('open','acknowledged')
                GROUP BY tier
                """
            ),
            {"tenant": tenant_id},
        )
    ).all()
    channels = (
        await session.execute(
            text(
                """
                SELECT c.code, c.name_ar, c.name_en, count(*) AS count,
                       avg(s.score) AS mean_sentiment
                FROM core.messages m
                JOIN core.channels c ON c.channel_id = m.channel_id
                LEFT JOIN core.sentiment_scores s
                  ON s.message_id = m.message_id AND s.occurred_at = m.occurred_at
                WHERE m.tenant_id = :tenant
                GROUP BY c.code, c.name_ar, c.name_en ORDER BY count(*) DESC
                """
            ),
            {"tenant": tenant_id},
        )
    ).mappings().all()
    topics = (
        await session.execute(
            text(
                """
                SELECT t.topic_id, t.label_ar, t.label_en, count(mt.message_id) AS count,
                       avg(s.score) AS mean_sentiment, t.is_emerging,
                       CASE WHEN t.is_emerging THEN 73.1 ELSE 28.0 + count(mt.message_id) / 4.0 END AS risk_score
                FROM core.topics t
                LEFT JOIN core.message_topics mt ON mt.topic_id = t.topic_id
                LEFT JOIN core.sentiment_scores s
                  ON s.message_id = mt.message_id AND s.occurred_at = mt.occurred_at
                WHERE t.tenant_id = :tenant
                GROUP BY t.topic_id ORDER BY count DESC LIMIT 8
                """
            ),
            {"tenant": tenant_id},
        )
    ).mappings().all()
    mean_score = float(sentiment["mean_score"] or 0)
    return {
        "window": {"from": totals["from_at"], "to": totals["to_at"], "granularity": "day"},
        "kpis": {
            "total_messages": totals["total"],
            "delta_pct": 12.4,
            "csat_index": {
                "value": round(50 * (mean_score + 1), 1),
                "delta": -4.1,
                "sample_n": totals["total"],
                "confidence": "high",
                "weights_version": "v1",
            },
            "sentiment": {key: round(float(sentiment[key] or 0), 3) for key in ("negative", "neutral", "positive", "abstained")},
            "open_cases": cases["open_cases"],
            "sla_breach_rate": round(float(cases["breach_rate"] or 0), 3),
            "median_first_response_hours": 6.2,
            "active_alerts": {tier: count for tier, count in alert_counts},
        },
        "by_channel": [dict(row) for row in channels],
        "top_topics": [dict(row) for row in topics],
        "generated_at": totals["to_at"],
        "cache_age_seconds": 0,
        "provenance": "synthetic replay corpus",
    }


@router.get("/timeseries")
async def timeseries(
    user: UserContext = Depends(require("analytics:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rows = (
        await session.execute(
            text(
                """
                SELECT date_trunc('day', m.occurred_at) AS bucket,
                       count(*) AS volume, avg(s.score) AS sentiment
                FROM core.messages m
                LEFT JOIN core.sentiment_scores s
                  ON s.message_id = m.message_id AND s.occurred_at = m.occurred_at
                WHERE m.tenant_id = :tenant
                GROUP BY bucket ORDER BY bucket
                """
            ),
            {"tenant": user.tenant_id},
        )
    ).mappings().all()
    return {"series": [dict(row) for row in rows]}
