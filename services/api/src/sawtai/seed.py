"""Seed the replay-backed prototype with deterministic synthetic records."""

import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import create_engine, text

from sawtai.config import postgres_url_with_driver

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000201")
ORG_ID = UUID("00000000-0000-0000-0000-000000000101")
MODEL_RUN_ID = UUID("00000000-0000-0000-0000-000000000711")
INFERENCE_RUN_ID = UUID("00000000-0000-0000-0000-000000000712")

CHANNELS = {
    "x": UUID("00000000-0000-0000-0000-000000000401"),
    "email": UUID("00000000-0000-0000-0000-000000000402"),
    "survey": UUID("00000000-0000-0000-0000-000000000403"),
    "whatsapp": UUID("00000000-0000-0000-0000-000000000404"),
}
SOURCES = {
    "x": UUID("00000000-0000-0000-0000-000000000501"),
    "email": UUID("00000000-0000-0000-0000-000000000502"),
    "survey": UUID("00000000-0000-0000-0000-000000000503"),
    "whatsapp": UUID("00000000-0000-0000-0000-000000000504"),
}
TOPICS = {
    "waste": UUID("00000000-0000-0000-0000-000000000701"),
    "roads": UUID("00000000-0000-0000-0000-000000000702"),
    "parks": UUID("00000000-0000-0000-0000-000000000703"),
    "permits": UUID("00000000-0000-0000-0000-000000000704"),
}
NODES = {
    "waste": UUID("00000000-0000-0000-0000-000000000601"),
    "roads": UUID("00000000-0000-0000-0000-000000000602"),
    "parks": UUID("00000000-0000-0000-0000-000000000603"),
    "permits": UUID("00000000-0000-0000-0000-000000000604"),
}

TEXTS = {
    "waste": [
        "صار لنا أربعة أيام والحاويات ممتلئة في المنطقة الصناعية <PHONE_1>",
        "نرجو معالجة تأخر جمع النفايات قبل أن تتفاقم المشكلة",
        "للأسف الرائحة أصبحت مزعجة جداً ونحتاج استجابة عاجلة",
        "تم تغيير موعد الجمع من دون إشعار السكان، نرجو التوضيح",
    ],
    "roads": [
        "الحفرة عند مدخل الحي ما زالت موجودة وتسبب ازدحاماً",
        "نرجو صيانة الإنارة في شارع الاتحاد حفاظاً على السلامة",
        "شكراً للفريق على سرعة إصلاح الإشارة المرورية",
    ],
    "parks": [
        "الحديقة جميلة ونشكر فرق البلدية على النظافة",
        "متى تعود ألعاب الأطفال للعمل في حديقة الحي؟",
        "نتمنى تمديد ساعات فتح الحديقة في عطلة نهاية الأسبوع",
    ],
    "permits": [
        "خدمة إصدار التصريح كانت سريعة وواضحة، شكراً لكم",
        "لم تصلني رسالة تحديث الطلب حتى الآن، أرجو المساعدة",
        "The permit portal is clear but the payment page timed out مرتين",
    ],
}


def database_url() -> str:
    value = os.environ.get(
        "ALEMBIC_DATABASE_URL",
        "postgresql+psycopg://sawtai:change-me-for-local-development@postgres:5432/sawtai",
    )
    return postgres_url_with_driver(value, "psycopg")


def stable_uuid(label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"https://sawtai.ae/demo/{label}")


def seed_static(connection: object) -> None:
    execute = connection.execute  # type: ignore[attr-defined]
    execute(
        text(
            """
            INSERT INTO core.tenants (tenant_id, code, name_ar, name_en)
            VALUES (:id, 'shj-demo', 'بلدية الشارقة التجريبية', 'Sharjah Municipality Demo')
            ON CONFLICT (tenant_id) DO NOTHING
            """
        ),
        {"id": TENANT_ID},
    )
    execute(
        text(
            """
            INSERT INTO core.org_units (org_unit_id, tenant_id, code, name_ar, name_en)
            VALUES (:id, :tenant, 'communications', 'إدارة الاتصال الحكومي', 'Government Communication')
            ON CONFLICT (org_unit_id) DO NOTHING
            """
        ),
        {"id": ORG_ID, "tenant": TENANT_ID},
    )
    execute(
        text(
            """
            INSERT INTO core.users (
                user_id, tenant_id, email, display_name_ar, display_name_en,
                org_unit_id, password_hash, mfa_enrolled
            ) VALUES (
                :id, :tenant, 'demo@sawtai.ae', 'مريم الكتبي', 'Maryam Al Ketbi',
                :org, 'demo-only', true
            ) ON CONFLICT (user_id) DO NOTHING
            """
        ),
        {"id": USER_ID, "tenant": TENANT_ID, "org": ORG_ID},
    )
    roles = [
        ("comms_officer", "Communication Officer", "مسؤول الاتصال", '["message:read","draft:create"]'),
        ("crisis_lead", "Crisis Lead", "مسؤول الأزمات", '["alert:read","alert:manage"]'),
    ]
    for index, (code, name_en, name_ar, permissions) in enumerate(roles, start=1):
        role_id = UUID(f"00000000-0000-0000-0000-{300 + index:012d}")
        execute(
            text(
                """
                INSERT INTO core.roles (role_id, code, name_en, name_ar, permissions)
                VALUES (:id, :code, :name_en, :name_ar, CAST(:permissions AS jsonb))
                ON CONFLICT (code) DO NOTHING
                """
            ),
            {
                "id": role_id,
                "code": code,
                "name_en": name_en,
                "name_ar": name_ar,
                "permissions": permissions,
            },
        )
        execute(
            text(
                """
                INSERT INTO core.user_roles (user_id, role_id, org_unit_id, granted_by)
                VALUES (:user_id, :role_id, :org_id, :user_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"user_id": USER_ID, "role_id": role_id, "org_id": ORG_ID},
        )

    channel_rows = [
        ("x", "social", "إكس", "X", True, "replay", "demo-x"),
        ("email", "email", "البريد الإلكتروني", "Email", False, "replay", "demo-email"),
        ("survey", "survey", "الاستبيانات", "Surveys", False, "replay", "demo-survey"),
        (
            "whatsapp",
            "social",
            "واتساب",
            "WhatsApp",
            False,
            "meta_whatsapp",
            "demo-whatsapp",
        ),
    ]
    for code, kind, name_ar, name_en, is_public, adapter, handle in channel_rows:
        execute(
            text(
                """
                INSERT INTO core.channels (
                    channel_id, tenant_id, kind, code, name_ar, name_en, is_public
                ) VALUES (:id, :tenant, CAST(:kind AS core.channel_kind), :code, :name_ar, :name_en, :public)
                ON CONFLICT (channel_id) DO NOTHING
                """
            ),
            {
                "id": CHANNELS[code],
                "tenant": TENANT_ID,
                "kind": kind,
                "code": code,
                "name_ar": name_ar,
                "name_en": name_en,
                "public": is_public,
            },
        )
        execute(
            text(
                """
                INSERT INTO core.sources (source_id, tenant_id, channel_id, adapter, config, handle)
                VALUES (:id, :tenant, :channel, :adapter, '{"speed": 8}', :handle)
                ON CONFLICT (source_id) DO NOTHING
                """
            ),
            {
                "id": SOURCES[code],
                "tenant": TENANT_ID,
                "channel": CHANNELS[code],
                "adapter": adapter,
                "handle": handle,
            },
        )

    taxonomy = [
        ("waste", "waste.collection.missed", "تأخر جمع النفايات", "Delayed waste collection", 4),
        ("roads", "roads.maintenance", "صيانة الطرق", "Road maintenance", 12),
        ("parks", "parks.facilities", "مرافق الحدائق", "Park facilities", 24),
        ("permits", "permits.digital", "التصاريح الرقمية", "Digital permits", 8),
    ]
    for key, code, label_ar, label_en, sla in taxonomy:
        execute(
            text(
                """
                INSERT INTO core.taxonomy_nodes (
                    node_id, tenant_id, code, label_ar, label_en, owner_org_unit_id, sla_hours
                ) VALUES (:id, :tenant, :code, :label_ar, :label_en, :org, :sla)
                ON CONFLICT (node_id) DO NOTHING
                """
            ),
            {
                "id": NODES[key],
                "tenant": TENANT_ID,
                "code": code,
                "label_ar": label_ar,
                "label_en": label_en,
                "org": ORG_ID,
                "sla": sla,
            },
        )

    topic_rows = [
        ("waste", "تأخر جمع النفايات", "Delayed waste collection", True),
        ("roads", "صيانة الطرق والإنارة", "Road and lighting maintenance", False),
        ("parks", "مرافق الحدائق", "Park facilities", False),
        ("permits", "الخدمات والتصاريح الرقمية", "Digital services and permits", False),
    ]
    first_seen = datetime(2026, 6, 10, tzinfo=UTC)
    last_seen = datetime(2026, 6, 16, tzinfo=UTC)
    for key, label_ar, label_en, emerging in topic_rows:
        execute(
            text(
                """
                INSERT INTO core.topics (
                    topic_id, tenant_id, model_run_id, label_ar, label_en,
                    keywords_ar, keywords_en, first_seen_at, last_seen_at,
                    message_count, is_emerging
                ) VALUES (
                    :id, :tenant, :run, :label_ar, :label_en,
                    :keywords_ar, :keywords_en, :first_seen, :last_seen, 60, :emerging
                ) ON CONFLICT (topic_id) DO NOTHING
                """
            ),
            {
                "id": TOPICS[key],
                "tenant": TENANT_ID,
                "run": MODEL_RUN_ID,
                "label_ar": label_ar,
                "label_en": label_en,
                "keywords_ar": [label_ar.split()[0], label_ar.split()[-1]],
                "keywords_en": label_en.lower().split()[:2],
                "first_seen": first_seen,
                "last_seen": last_seen,
                "emerging": emerging,
            },
        )

    playbook_id = UUID("00000000-0000-0000-0000-000000000801")
    execute(
        text(
            """
            INSERT INTO core.playbooks (
                playbook_id, tenant_id, code, title_ar, title_en, trigger_tier, steps
            ) VALUES (
                :id, :tenant, 'service-disruption', 'بروتوكول انقطاع الخدمة',
                'Service disruption protocol', 'high',
                CAST(:steps AS jsonb)
            ) ON CONFLICT (playbook_id) DO NOTHING
            """
        ),
        {
            "id": playbook_id,
            "tenant": TENANT_ID,
            "steps": '[{"seq":1,"action_ar":"إبلاغ مدير الإدارة","owner_role":"dept_head"},{"seq":2,"action_ar":"إعداد بيان أولي","owner_role":"comms_officer"}]',
        },
    )

    document_id = UUID("00000000-0000-0000-0000-000000000d01")
    chunk_id = UUID("00000000-0000-0000-0000-000000000e01")
    policy_text = (
        "تستقبل البلدية بلاغات تأخر جمع النفايات على مدار الساعة. "
        "يُسجّل البلاغ فور استلامه ويُحال إلى الفريق المختص، وتتم متابعة الحالة وفق "
        "جدول الخدمة المعتمد. يجب تزويد البلدية برقم مرجع الطلب عند طلب متابعة حالة محددة."
    )
    execute(
        text(
            """
            INSERT INTO core.documents (
                document_id, tenant_id, kind, title_ar, title_en, lang,
                version, effective_from, is_approved, approved_by, object_key, sha256
            ) VALUES (
                :document_id, :tenant_id, 'service_guide',
                'دليل بلاغات جمع النفايات', 'Waste Collection Reports Guide', 'ar',
                '1', '2026-01-01', true, :approved_by,
                'seed/policies/waste-collection-guide-v1.pdf', :sha256
            ) ON CONFLICT (document_id) DO NOTHING
            """
        ),
        {
            "document_id": document_id,
            "tenant_id": TENANT_ID,
            "approved_by": USER_ID,
            "sha256": hashlib.sha256(policy_text.encode()).digest(),
        },
    )
    execute(
        text(
            """
            INSERT INTO core.doc_chunks (
                chunk_id, tenant_id, document_id, seq, heading_path, text,
                norm_text, token_count, lang, embedding, tsv
            ) VALUES (
                :chunk_id, :tenant_id, :document_id, 1,
                'خدمات النفايات > البلاغات والمتابعة', :text, :norm_text,
                54, 'ar', array_fill(0.0::real, ARRAY[1024])::vector,
                to_tsvector('simple', :norm_text)
            ) ON CONFLICT (chunk_id) DO NOTHING
            """
        ),
        {
            "chunk_id": chunk_id,
            "tenant_id": TENANT_ID,
            "document_id": document_id,
            "text": policy_text,
            "norm_text": policy_text,
        },
    )
    execute(
        text(
            """
            INSERT INTO core.alerts (
                alert_id, tenant_id, topic_id, node_id, tier, risk_score, drivers,
                window_start, window_end, title_ar, title_en, playbook_id,
                model_name, model_version
            ) VALUES (
                '00000000-0000-0000-0000-000000000901', :tenant, :topic, :node,
                'high', 73.1,
                CAST(:drivers AS jsonb),
                '2026-06-11 14:00:00+00', '2026-06-14 18:00:00+00',
                'تصاعد شكاوى تأخر جمع النفايات', 'Escalating delayed waste collection complaints',
                :playbook, 'crisis-composite', 'v1.2'
            ) ON CONFLICT (alert_id) DO NOTHING
            """
        ),
        {
            "tenant": TENANT_ID,
            "topic": TOPICS["waste"],
            "node": NODES["waste"],
            "playbook": playbook_id,
            "drivers": '[{"feature":"volume_ratio","value":5.2,"contribution":0.30},{"feature":"neg_velocity","value":0.31,"contribution":0.28},{"feature":"breadth","value":89,"contribution":0.16},{"feature":"novelty","value":0.74,"contribution":0.14},{"feature":"amplification","value":1420,"contribution":0.12}]',
        },
    )


def seed_messages(connection: object) -> None:
    execute = connection.execute  # type: ignore[attr-defined]
    existing = execute(
        text("SELECT count(*) FROM core.messages WHERE tenant_id = :tenant"),
        {"tenant": TENANT_ID},
    ).scalar_one()
    if existing:
        return

    start = datetime(2026, 6, 10, 6, tzinfo=UTC)
    keys = ("waste", "roads", "parks", "permits")
    channels = ("x", "x", "email", "survey")
    message_rows: list[dict[str, object]] = []
    sentiment_rows: list[dict[str, object]] = []
    classification_rows: list[dict[str, object]] = []
    topic_rows: list[dict[str, object]] = []

    for index in range(240):
        key = keys[index % len(keys)]
        channel = channels[index % len(channels)]
        if index >= 144 and index % 3 != 0:
            key = "waste"
            channel = "x"
        content = TEXTS[key][index % len(TEXTS[key])]
        message_id = stable_uuid(f"message-{index}")
        occurred_at = start + timedelta(minutes=index * 36)
        negative = key == "waste" or (key == "roads" and index % 3 != 0)
        positive = key in {"parks", "permits"} and index % 3 == 0
        label = "negative" if negative else "positive" if positive else "neutral"
        score = -0.78 if negative else 0.72 if positive else 0.04
        digest = hashlib.sha256(f"{content}:{index}".encode()).digest()
        simhash = int.from_bytes(digest[:8], "big", signed=True)
        message_rows.append(
            {
                "message_id": message_id,
                "tenant_id": TENANT_ID,
                "source_id": SOURCES[channel],
                "channel_id": CHANNELS[channel],
                "external_id": f"replay-{index:05d}",
                "occurred_at": occurred_at,
                "author_pseudonym": hashlib.sha256(f"author-{index % 91}".encode()).hexdigest()[:32],
                "raw_text": content,
                "norm_text": content,
                "lang": "mixed" if "The " in content else "ar",
                "code_switch": 0.22 if "The " in content else 0.0,
                "dialect": "gulf" if index % 4 != 0 else "msa",
                "content_hash": digest,
                "simhash": simhash,
                "engagement": f'{{"likes":{3 + index % 41},"reposts":{index % 17},"replies":{index % 9}}}',
            }
        )
        sentiment_rows.append(
            {
                "tenant_id": TENANT_ID,
                "message_id": message_id,
                "occurred_at": occurred_at,
                "label": label,
                "score": score,
                "prob_neg": 0.91 if negative else 0.05,
                "prob_neu": 0.84 if label == "neutral" else 0.06,
                "prob_pos": 0.89 if positive else 0.03,
                "dialect": "gulf" if index % 4 != 0 else "msa",
            }
        )
        classification_rows.append(
            {
                "tenant_id": TENANT_ID,
                "message_id": message_id,
                "occurred_at": occurred_at,
                "node_id": NODES[key],
                "confidence": 0.82 + (index % 12) / 100,
            }
        )
        topic_rows.append(
            {
                "message_id": message_id,
                "occurred_at": occurred_at,
                "topic_id": TOPICS[key],
                "similarity": 0.74 + (index % 15) / 100,
            }
        )

    execute(
        text(
            """
            INSERT INTO core.messages (
                message_id, tenant_id, source_id, channel_id, external_id, occurred_at,
                author_pseudonym, raw_text, norm_text, lang_primary, code_switch_ratio,
                dialect, dialect_conf, content_hash, simhash, engagement, enrichment_state
            ) VALUES (
                :message_id, :tenant_id, :source_id, :channel_id, :external_id, :occurred_at,
                :author_pseudonym, :raw_text, :norm_text, CAST(:lang AS core.lang_code), :code_switch,
                CAST(:dialect AS core.dialect_code), 0.88, :content_hash, :simhash,
                CAST(:engagement AS jsonb), 15
            )
            """
        ),
        message_rows,
    )
    execute(
        text(
            """
            INSERT INTO core.sentiment_scores (
                tenant_id, message_id, occurred_at, label, score, prob_neg, prob_neu,
                prob_pos, dialect_at_score, model_name, model_version, inference_run_id
            ) VALUES (
                :tenant_id, :message_id, :occurred_at, CAST(:label AS core.sentiment_label),
                :score, :prob_neg, :prob_neu, :prob_pos, CAST(:dialect AS core.dialect_code),
                'marbertv2-sent', '2026.08.demo', :run
            )
            """
        ),
        [{**row, "run": INFERENCE_RUN_ID} for row in sentiment_rows],
    )
    execute(
        text(
            """
            INSERT INTO core.classifications (
                tenant_id, message_id, occurred_at, node_id, confidence, model_name,
                model_version, inference_run_id
            ) VALUES (
                :tenant_id, :message_id, :occurred_at, :node_id, :confidence,
                'marbertv2-taxonomy', '2026.08.demo', :run
            )
            """
        ),
        [{**row, "run": INFERENCE_RUN_ID} for row in classification_rows],
    )
    execute(
        text(
            """
            INSERT INTO core.message_topics (message_id, occurred_at, topic_id, similarity)
            VALUES (:message_id, :occurred_at, :topic_id, :similarity)
            """
        ),
        topic_rows,
    )

    for hour in range(108):
        bucket = start + timedelta(hours=hour)
        ratio = hour / 107
        count = max(3, int(4 + ratio**3 * 186))
        negative_count = int(count * (0.42 + ratio * 0.39))
        execute(
            text(
                """
                INSERT INTO core.topic_timeseries (
                    tenant_id, topic_id, bucket_start, msg_count, neg_count,
                    mean_sentiment, unique_authors, engagement_sum, novelty
                ) VALUES (
                    :tenant, :topic, :bucket, :count, :negative, :sentiment,
                    :authors, :engagement, :novelty
                ) ON CONFLICT DO NOTHING
                """
            ),
            {
                "tenant": TENANT_ID,
                "topic": TOPICS["waste"],
                "bucket": bucket,
                "count": count,
                "negative": negative_count,
                "sentiment": -0.25 - ratio * 0.53,
                "authors": max(3, int(count * 0.62)),
                "engagement": count * (4 + hour // 12),
                "novelty": 0.22 + ratio * 0.58,
            },
        )


def seed_workflow(connection: object) -> None:
    execute = connection.execute  # type: ignore[attr-defined]
    case_id = UUID("00000000-0000-0000-0000-000000000a01")
    response_id = UUID("00000000-0000-0000-0000-000000000c01")
    execute(
        text(
            """
            INSERT INTO core.cases (
                case_id, tenant_id, reference, title_ar, title_en, node_id,
                org_unit_id, assigned_to, status, severity, sla_due_at, complaint_count
            ) VALUES (
                :id, :tenant, 'SHJ-2026-004182', 'تأخر جمع النفايات في المنطقة الصناعية',
                'Delayed waste collection in Industrial Area', :node, :org, :user,
                'awaiting_response', 'high', '2026-06-15 12:00:00+00', 47
            ) ON CONFLICT (case_id) DO NOTHING
            """
        ),
        {"id": case_id, "tenant": TENANT_ID, "node": NODES["waste"], "org": ORG_ID, "user": USER_ID},
    )
    execute(
        text(
            """
            INSERT INTO core.responses (
                response_id, tenant_id, case_id, alert_id, kind, lang, audience,
                body, status, generated_by_model, model_version, prompt_version,
                grounding_score, created_by, approved_by, approved_at
            ) VALUES (
                :id, :tenant, :case_id, '00000000-0000-0000-0000-000000000901',
                'reply', 'ar', 'citizen',
                'نشكركم على تواصلكم. تم تحديث جدول جمع النفايات في المنطقة الصناعية، وقد وُجّه الفريق المختص لمعالجة التراكم خلال الساعات القادمة.',
                'approved', 'demo-grounded-generator', 'v1', 'reply-ar-v1', 0.94,
                :user, :user, '2026-06-14 09:41:22+00'
            ) ON CONFLICT (response_id) DO NOTHING
            """
        ),
        {"id": response_id, "tenant": TENANT_ID, "case_id": case_id, "user": USER_ID},
    )
    row_hash = hashlib.sha256(b"sawtai-demo-audit-chain-head").digest()
    execute(
        text(
            """
            INSERT INTO core.audit_log (
                tenant_id, occurred_at, actor_user_id, actor_type, action,
                object_type, object_id, outcome, after_state, row_hash
            ) SELECT
                :tenant, '2026-06-14 09:41:22+00', :user, 'user',
                'response.approve', 'response', :response, 'success',
                '{"status":"approved"}', :hash
            WHERE NOT EXISTS (
                SELECT 1 FROM core.audit_log WHERE object_id = :response
            )
            """
        ),
        {"tenant": TENANT_ID, "user": USER_ID, "response": response_id, "hash": row_hash},
    )


def main() -> None:
    engine = create_engine(database_url())
    with engine.begin() as connection:
        seed_static(connection)
        seed_messages(connection)
        seed_workflow(connection)
    print("SawtAI demo seed complete")


if __name__ == "__main__":
    main()
