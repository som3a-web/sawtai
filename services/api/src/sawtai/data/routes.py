from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.auth.service import UserContext, require
from sawtai.database import get_session

router = APIRouter(prefix="/api/v1/data", tags=["data"])


@dataclass(frozen=True)
class Dataset:
    name: str
    label_ar: str
    label_en: str
    description_ar: str
    description_en: str
    query: str


DATASETS = {
    dataset.name: dataset
    for dataset in (
        Dataset(
            "messages",
            "الرسائل",
            "Messages",
            "النصوص الواردة بعد إخفاء هوية أصحابها",
            "Incoming citizen text with pseudonymised authors",
            """
            SELECT message_id, occurred_at, lang_primary, dialect, raw_text, engagement
            FROM core.messages WHERE tenant_id = :tenant
            ORDER BY occurred_at DESC LIMIT :limit
            """,
        ),
        Dataset(
            "sentiment_scores",
            "تحليل المشاعر",
            "Sentiment scores",
            "نتائج المشاعر مع احتمالات النموذج",
            "Model sentiment results and probabilities",
            """
            SELECT message_id, occurred_at, label, score, prob_neg, prob_neu, prob_pos,
                   model_name, model_version, is_abstained
            FROM core.sentiment_scores WHERE tenant_id = :tenant
            ORDER BY occurred_at DESC LIMIT :limit
            """,
        ),
        Dataset(
            "classifications",
            "التصنيفات",
            "Classifications",
            "تصنيف الرسائل وفق شجرة الخدمات",
            "Message classification against the service taxonomy",
            """
            SELECT c.message_id, c.occurred_at, n.code AS node_code, n.label_ar,
                   n.label_en, c.confidence, c.model_name, c.model_version,
                   c.reviewed_at
            FROM core.classifications c
            JOIN core.taxonomy_nodes n ON n.node_id = c.node_id
            WHERE c.tenant_id = :tenant
            ORDER BY c.occurred_at DESC LIMIT :limit
            """,
        ),
        Dataset(
            "topics",
            "المواضيع",
            "Topics",
            "المواضيع المكتشفة وحالتها الصاعدة",
            "Detected topics and emerging-topic status",
            """
            SELECT topic_id, label_ar, label_en, message_count, is_emerging,
                   first_seen_at, last_seen_at
            FROM core.topics WHERE tenant_id = :tenant
            ORDER BY message_count DESC LIMIT :limit
            """,
        ),
        Dataset(
            "topic_timeseries",
            "السلسلة الزمنية",
            "Topic timeseries",
            "حجم الموضوع والمشاعر والمخاطر عبر الزمن",
            "Topic volume, sentiment, and risk features over time",
            """
            SELECT bucket_start, msg_count, neg_count, mean_sentiment,
                   unique_authors, engagement_sum, novelty
            FROM core.topic_timeseries WHERE tenant_id = :tenant
            ORDER BY bucket_start DESC LIMIT :limit
            """,
        ),
        Dataset(
            "alerts",
            "التنبيهات",
            "Alerts",
            "تنبيهات المخاطر ومحركاتها القابلة للتفسير",
            "Risk alerts and their explainable drivers",
            """
            SELECT alert_id, created_at, tier, risk_score, title_ar, title_en,
                   status, drivers, model_name, model_version
            FROM core.alerts WHERE tenant_id = :tenant
            ORDER BY created_at DESC LIMIT :limit
            """,
        ),
        Dataset(
            "cases",
            "الحالات",
            "Cases",
            "الحالات التشغيلية وحالة اتفاقية الخدمة",
            "Operational cases and SLA status",
            """
            SELECT case_id, reference, title_ar, title_en, status, severity,
                   complaint_count, sla_due_at, created_at
            FROM core.cases WHERE tenant_id = :tenant
            ORDER BY created_at DESC LIMIT :limit
            """,
        ),
        Dataset(
            "responses",
            "الردود",
            "Responses",
            "المسودات والردود المعتمدة وسجل اعتمادها",
            "Draft and approved responses with approval lineage",
            """
            SELECT response_id, case_id, kind, lang, audience, body, status,
                   generated_by_model, grounding_score, created_at, approved_at
            FROM core.responses WHERE tenant_id = :tenant
            ORDER BY created_at DESC LIMIT :limit
            """,
        ),
        Dataset(
            "channels",
            "القنوات",
            "Channels",
            "قنوات التواصل المسجلة في المنصة",
            "Communication channels registered in the platform",
            """
            SELECT channel_id, kind, code, name_ar, name_en, is_public
            FROM core.channels WHERE tenant_id = :tenant
            ORDER BY code LIMIT :limit
            """,
        ),
        Dataset(
            "taxonomy_nodes",
            "شجرة الخدمات",
            "Taxonomy nodes",
            "فئات الخدمات والجهات المالكة والمهل",
            "Service categories, owners, and SLAs",
            """
            SELECT node_id, code, label_ar, label_en, sla_hours, is_active
            FROM core.taxonomy_nodes WHERE tenant_id = :tenant
            ORDER BY code LIMIT :limit
            """,
        ),
        Dataset(
            "audit_log",
            "سجل التدقيق",
            "Audit log",
            "سجل غير قابل للتعديل للعمليات الحساسة",
            "Append-only record of sensitive actions",
            """
            SELECT audit_id, occurred_at, actor_type, action, object_type,
                   object_id, outcome, request_id
            FROM core.audit_log WHERE tenant_id = :tenant
            ORDER BY occurred_at DESC LIMIT :limit
            """,
        ),
    )
}


@router.get("/tables")
async def tables(
    user: UserContext = Depends(require("data:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    items = []
    for dataset in DATASETS.values():
        count = (
            await session.execute(
                text(f"SELECT count(*) FROM core.{dataset.name} WHERE tenant_id = :tenant"),
                {"tenant": user.tenant_id},
            )
        ).scalar_one()
        items.append(
            {
                "name": dataset.name,
                "schema": "core",
                "label_ar": dataset.label_ar,
                "label_en": dataset.label_en,
                "description_ar": dataset.description_ar,
                "description_en": dataset.description_en,
                "row_count": count,
            }
        )
    return {
        "database": "sawtai",
        "schema": "core",
        "mode": "read_only",
        "items": items,
        "restricted_schema_visible": False,
    }


@router.get("/tables/{table_name}")
async def table_rows(
    table_name: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: UserContext = Depends(require("data:read")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    dataset = DATASETS.get(table_name)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset is not available")
    rows = (
        await session.execute(
            text(dataset.query),
            {"tenant": user.tenant_id, "limit": limit},
        )
    ).mappings().all()
    columns = list(rows[0].keys()) if rows else []
    return {
        "name": dataset.name,
        "label_ar": dataset.label_ar,
        "label_en": dataset.label_en,
        "columns": columns,
        "rows": [dict(row) for row in rows],
        "limit": limit,
        "mode": "read_only",
    }
