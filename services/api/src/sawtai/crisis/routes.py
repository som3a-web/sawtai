from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.auth.service import UserContext, require
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1", tags=["crisis"])


@router.get("/alerts")
async def alerts(
    user: UserContext = Depends(require("alert:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rows = (
        await session.execute(
            text(
                """
                SELECT a.alert_id, a.tier::text, a.risk_score, a.drivers,
                       a.window_start, a.window_end, a.title_ar, a.title_en,
                       a.status::text, a.model_name, a.model_version,
                       t.topic_id, t.label_ar AS topic_label_ar, t.label_en AS topic_label_en,
                       p.title_ar AS playbook_title_ar, p.steps AS playbook_steps
                FROM core.alerts a
                LEFT JOIN core.topics t ON t.topic_id = a.topic_id
                LEFT JOIN core.playbooks p ON p.playbook_id = a.playbook_id
                WHERE a.tenant_id = :tenant ORDER BY a.risk_score DESC
                """
            ),
            {"tenant": user.tenant_id},
        )
    ).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/forecast/replay")
async def replay(
    user: UserContext = Depends(require("alert:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    rows = (
        await session.execute(
            text(
                """
                SELECT ts.bucket_start, ts.msg_count, ts.neg_count, ts.mean_sentiment,
                       ts.unique_authors, ts.engagement_sum, ts.novelty,
                       t.topic_id, t.label_ar, t.label_en
                FROM core.topic_timeseries ts
                JOIN core.topics t ON t.topic_id = ts.topic_id
                WHERE ts.tenant_id = :tenant AND t.is_emerging
                ORDER BY ts.bucket_start
                """
            ),
            {"tenant": user.tenant_id},
        )
    ).mappings().all()
    maximum = max((row["msg_count"] for row in rows), default=1)
    series = []
    first_alert = None
    for row in rows:
        ratio = row["msg_count"] / maximum
        negative_share = row["neg_count"] / max(row["msg_count"], 1)
        risk = round(min(96.0, 18 + ratio * 52 + negative_share * 18 + float(row["novelty"] or 0) * 10), 1)
        tier = "critical" if risk >= 85 else "high" if risk >= 70 else "elevated" if risk >= 55 else "watch" if risk >= 40 else None
        if first_alert is None and risk >= 55:
            first_alert = row["bucket_start"]
        series.append(
            {
                "t": row["bucket_start"],
                "msg_count": row["msg_count"],
                "neg_share": round(negative_share, 3),
                "risk_score": risk,
                "tier": tier,
            }
        )
    peak = rows[-1]["bucket_start"] if rows else None
    lead_time = round((peak - first_alert).total_seconds() / 3600, 1) if peak and first_alert else 0
    return {
        "topic_id": rows[0]["topic_id"] if rows else None,
        "label_ar": rows[0]["label_ar"] if rows else "",
        "label_en": rows[0]["label_en"] if rows else "",
        "series": series,
        "first_alert_at": first_alert,
        "observed_peak_at": peak,
        "lead_time_hours": lead_time,
        "method": "transparent composite index over synthetic replay data",
    }
