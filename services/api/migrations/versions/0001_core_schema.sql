-- SawtAI authoritative PostgreSQL schema from ARCHITECTURE.md section 4.3.
-- PostgreSQL 16 + pgvector >= 0.7.

-- ============================================================
-- EXTENSIONS & CONVENTIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
-- Required by the users.email type in the authoritative schema.
CREATE EXTENSION IF NOT EXISTS "citext";

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS restricted;
SET search_path = core, public;

-- ============================================================
-- ORG / IDENTITY / RBAC
-- ============================================================
CREATE TABLE tenants (
    tenant_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT NOT NULL UNIQUE,
    name_ar         TEXT NOT NULL,
    name_en         TEXT NOT NULL,
    data_region     TEXT NOT NULL DEFAULT 'ae-shj',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE org_units (
    org_unit_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    parent_id       UUID REFERENCES org_units,
    code            TEXT NOT NULL,
    name_ar         TEXT NOT NULL,
    name_en         TEXT NOT NULL,
    UNIQUE (tenant_id, code)
);
CREATE INDEX ix_org_units_tenant_parent ON org_units (tenant_id, parent_id);

CREATE TABLE users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    external_sub    TEXT,
    email           CITEXT NOT NULL,
    display_name_ar TEXT,
    display_name_en TEXT,
    org_unit_id     UUID REFERENCES org_units,
    password_hash   TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    mfa_enrolled    BOOLEAN NOT NULL DEFAULT FALSE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email)
);
CREATE UNIQUE INDEX ux_users_external_sub ON users (external_sub)
    WHERE external_sub IS NOT NULL;

CREATE TABLE roles (
    role_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT NOT NULL UNIQUE,
    name_en         TEXT NOT NULL,
    name_ar         TEXT NOT NULL,
    permissions     JSONB NOT NULL DEFAULT '[]'
);

CREATE TABLE user_roles (
    user_id         UUID NOT NULL REFERENCES users ON DELETE CASCADE,
    role_id         UUID NOT NULL REFERENCES roles,
    org_unit_id     UUID REFERENCES org_units,
    granted_by      UUID REFERENCES users,
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- PostgreSQL forbids expressions in PRIMARY KEY declarations. This unique
-- expression index implements the exact identity rule specified in section 4.3.
CREATE UNIQUE INDEX ux_user_roles_identity ON user_roles (
    user_id,
    role_id,
    COALESCE(org_unit_id, '00000000-0000-0000-0000-000000000000'::uuid)
);

-- ============================================================
-- CHANNELS & SOURCES
-- ============================================================
CREATE TYPE channel_kind AS ENUM
    ('social','email','webform','survey','call_center','news','crm');

CREATE TABLE channels (
    channel_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    kind            channel_kind NOT NULL,
    code            TEXT NOT NULL,
    name_ar         TEXT NOT NULL,
    name_en         TEXT NOT NULL,
    is_public       BOOLEAN NOT NULL,
    UNIQUE (tenant_id, code)
);

CREATE TABLE sources (
    source_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    channel_id      UUID NOT NULL REFERENCES channels,
    adapter         TEXT NOT NULL,
    config          JSONB NOT NULL DEFAULT '{}',
    handle          TEXT,
    is_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    last_cursor     TEXT,
    last_polled_at  TIMESTAMPTZ,
    UNIQUE (tenant_id, channel_id, handle)
);
CREATE INDEX ix_sources_enabled ON sources (tenant_id, is_enabled)
    WHERE is_enabled;

-- ============================================================
-- MESSAGES (partitioned by RANGE on occurred_at, monthly)
-- ============================================================
CREATE TYPE lang_code AS ENUM ('ar','en','mixed','other');
CREATE TYPE dialect_code AS ENUM
    ('msa','gulf','levantine','egyptian','maghrebi','unknown');
CREATE TYPE data_tier AS ENUM ('c0_public','c1_internal','c2_personal','c3_restricted');

CREATE TABLE messages (
    message_id        UUID        NOT NULL DEFAULT gen_random_uuid(),
    tenant_id         UUID        NOT NULL,
    source_id         UUID        NOT NULL,
    channel_id        UUID        NOT NULL,
    external_id       TEXT,
    parent_external_id TEXT,
    occurred_at       TIMESTAMPTZ NOT NULL,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    author_pseudonym  CHAR(32)    NOT NULL,
    author_follower_bucket SMALLINT,
    raw_text          TEXT        NOT NULL,
    norm_text         TEXT        NOT NULL,
    lang_primary      lang_code   NOT NULL,
    code_switch_ratio REAL        NOT NULL DEFAULT 0,
    dialect           dialect_code NOT NULL DEFAULT 'unknown',
    dialect_conf      REAL,
    content_hash      BYTEA       NOT NULL,
    simhash           BIGINT      NOT NULL,
    duplicate_of      UUID,
    data_tier         data_tier   NOT NULL DEFAULT 'c2_personal',
    raw_object_key    TEXT,
    engagement        JSONB       NOT NULL DEFAULT '{}',
    tsv               tsvector,
    embedding         vector(1024),
    enrichment_state  SMALLINT    NOT NULL DEFAULT 0,
    PRIMARY KEY (message_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE messages_2026_06 PARTITION OF messages
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE messages_2026_07 PARTITION OF messages
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE messages_2026_08 PARTITION OF messages
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE messages_2026_09 PARTITION OF messages
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE messages_default PARTITION OF messages DEFAULT;

CREATE UNIQUE INDEX ux_messages_dedup
    ON messages (tenant_id, content_hash, occurred_at);
CREATE INDEX ix_messages_tenant_time
    ON messages (tenant_id, occurred_at DESC);
CREATE INDEX ix_messages_channel_time
    ON messages (tenant_id, channel_id, occurred_at DESC);
CREATE INDEX ix_messages_author
    ON messages (tenant_id, author_pseudonym, occurred_at DESC);
CREATE INDEX ix_messages_tsv ON messages USING gin (tsv);
CREATE INDEX ix_messages_trgm ON messages USING gin (norm_text gin_trgm_ops);
CREATE INDEX ix_messages_simhash ON messages ((simhash >> 48));
CREATE INDEX ix_messages_pending
    ON messages (tenant_id, enrichment_state)
    WHERE enrichment_state < 15;
CREATE INDEX ix_messages_embedding ON messages
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);

-- ============================================================
-- PII VAULT (restricted schema, separate grants)
-- ============================================================
CREATE TABLE restricted.pii_vault (
    author_pseudonym  CHAR(32) PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    native_id_enc     BYTEA NOT NULL,
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    erasure_requested_at TIMESTAMPTZ
);
REVOKE ALL ON restricted.pii_vault FROM PUBLIC;

CREATE TABLE pii_findings (
    finding_id      BIGSERIAL PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    message_id      UUID NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    entity_type     TEXT NOT NULL,
    start_offset    INT NOT NULL,
    end_offset      INT NOT NULL,
    confidence      REAL NOT NULL,
    recogniser      TEXT NOT NULL
);
CREATE INDEX ix_pii_findings_msg ON pii_findings (tenant_id, message_id);

-- ============================================================
-- ENTITIES (bilingual named entities)
-- ============================================================
CREATE TABLE entities (
    entity_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    entity_type     TEXT NOT NULL,
    canonical_ar    TEXT NOT NULL,
    canonical_en    TEXT NOT NULL,
    aliases         TEXT[] NOT NULL DEFAULT '{}',
    org_unit_id     UUID REFERENCES org_units,
    UNIQUE (tenant_id, entity_type, canonical_en)
);
CREATE INDEX ix_entities_alias ON entities USING gin (aliases);
CREATE INDEX ix_entities_ar_trgm ON entities USING gin (canonical_ar gin_trgm_ops);

CREATE TABLE message_entities (
    message_id      UUID NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    entity_id       UUID NOT NULL REFERENCES entities,
    mention_text    TEXT NOT NULL,
    start_offset    INT,
    end_offset      INT,
    confidence      REAL NOT NULL,
    PRIMARY KEY (message_id, occurred_at, entity_id, start_offset)
);
CREATE INDEX ix_message_entities_entity ON message_entities (entity_id, occurred_at DESC);

-- ============================================================
-- CLASSIFICATIONS (taxonomy assignment + routing)
-- ============================================================
CREATE TABLE taxonomy_nodes (
    node_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    parent_id       UUID REFERENCES taxonomy_nodes,
    code            TEXT NOT NULL,
    label_ar        TEXT NOT NULL,
    label_en        TEXT NOT NULL,
    owner_org_unit_id UUID REFERENCES org_units,
    sla_hours       INT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (tenant_id, code)
);

CREATE TABLE classifications (
    classification_id BIGSERIAL,
    tenant_id       UUID NOT NULL,
    message_id      UUID NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    node_id         UUID NOT NULL REFERENCES taxonomy_nodes,
    confidence      REAL NOT NULL,
    rank            SMALLINT NOT NULL DEFAULT 1,
    is_abstained    BOOLEAN NOT NULL DEFAULT FALSE,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    inference_run_id UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by     UUID REFERENCES users,
    reviewed_node_id UUID REFERENCES taxonomy_nodes,
    reviewed_at     TIMESTAMPTZ,
    PRIMARY KEY (classification_id, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE TABLE classifications_2026_06 PARTITION OF classifications
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE classifications_2026_07 PARTITION OF classifications
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE classifications_2026_08 PARTITION OF classifications
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE classifications_2026_09 PARTITION OF classifications
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE classifications_default PARTITION OF classifications DEFAULT;
CREATE INDEX ix_classifications_msg ON classifications (tenant_id, message_id);
CREATE INDEX ix_classifications_node
    ON classifications (tenant_id, node_id, occurred_at DESC) WHERE rank = 1;
CREATE INDEX ix_classifications_review_queue
    ON classifications (tenant_id, confidence)
    WHERE rank = 1 AND reviewed_at IS NULL AND is_abstained;

-- ============================================================
-- SENTIMENT
-- ============================================================
CREATE TYPE sentiment_label AS ENUM ('negative','neutral','positive');

CREATE TABLE sentiment_scores (
    sentiment_id    BIGSERIAL,
    tenant_id       UUID NOT NULL,
    message_id      UUID NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    label           sentiment_label NOT NULL,
    score           REAL NOT NULL,
    prob_neg        REAL NOT NULL,
    prob_neu        REAL NOT NULL,
    prob_pos        REAL NOT NULL,
    is_abstained    BOOLEAN NOT NULL DEFAULT FALSE,
    sarcasm_flag    BOOLEAN NOT NULL DEFAULT FALSE,
    dialect_at_score dialect_code NOT NULL,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    inference_run_id UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (sentiment_id, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE TABLE sentiment_scores_2026_06 PARTITION OF sentiment_scores
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE sentiment_scores_2026_07 PARTITION OF sentiment_scores
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE sentiment_scores_2026_08 PARTITION OF sentiment_scores
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE sentiment_scores_2026_09 PARTITION OF sentiment_scores
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE sentiment_scores_default PARTITION OF sentiment_scores DEFAULT;
CREATE UNIQUE INDEX ux_sentiment_msg_model
    ON sentiment_scores (tenant_id, message_id, model_name, model_version, occurred_at);
CREATE INDEX ix_sentiment_time
    ON sentiment_scores (tenant_id, occurred_at DESC, label);

-- ============================================================
-- TOPICS
-- ============================================================
CREATE TABLE topics (
    topic_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    model_run_id    UUID NOT NULL,
    label_ar        TEXT NOT NULL,
    label_en        TEXT NOT NULL,
    keywords_ar     TEXT[] NOT NULL DEFAULT '{}',
    keywords_en     TEXT[] NOT NULL DEFAULT '{}',
    centroid        vector(1024),
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    message_count   INT NOT NULL DEFAULT 0,
    is_emerging     BOOLEAN NOT NULL DEFAULT FALSE,
    merged_into     UUID REFERENCES topics,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_topics_tenant_last ON topics (tenant_id, last_seen_at DESC);
CREATE INDEX ix_topics_centroid ON topics
    USING hnsw (centroid vector_cosine_ops) WITH (m=16, ef_construction=64);

CREATE TABLE message_topics (
    message_id      UUID NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    topic_id        UUID NOT NULL REFERENCES topics,
    similarity      REAL NOT NULL,
    PRIMARY KEY (message_id, occurred_at, topic_id)
);
CREATE INDEX ix_message_topics_topic ON message_topics (topic_id, occurred_at DESC);

CREATE TABLE topic_timeseries (
    tenant_id       UUID NOT NULL,
    topic_id        UUID NOT NULL,
    bucket_start    TIMESTAMPTZ NOT NULL,
    msg_count       INT NOT NULL DEFAULT 0,
    neg_count       INT NOT NULL DEFAULT 0,
    mean_sentiment  REAL,
    unique_authors  INT NOT NULL DEFAULT 0,
    engagement_sum  BIGINT NOT NULL DEFAULT 0,
    novelty         REAL,
    PRIMARY KEY (tenant_id, topic_id, bucket_start)
);
CREATE INDEX ix_topic_ts_bucket ON topic_timeseries (tenant_id, bucket_start DESC);

-- ============================================================
-- COMPLAINTS & CASES
-- ============================================================
CREATE TYPE complaint_severity AS ENUM ('low','medium','high','critical');
CREATE TYPE case_status AS ENUM
    ('new','triaged','assigned','awaiting_response','responded','resolved','closed','rejected');

CREATE TABLE complaints (
    complaint_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    message_id      UUID NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    node_id         UUID REFERENCES taxonomy_nodes,
    severity        complaint_severity NOT NULL DEFAULT 'medium',
    issue_summary_ar TEXT,
    issue_summary_en TEXT,
    location_text   TEXT,
    location_entity_id UUID REFERENCES entities,
    is_actionable   BOOLEAN NOT NULL DEFAULT TRUE,
    case_id         UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_complaints_case ON complaints (case_id);
CREATE INDEX ix_complaints_open ON complaints (tenant_id, created_at DESC)
    WHERE case_id IS NULL;

CREATE TABLE cases (
    case_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    reference       TEXT NOT NULL,
    title_ar        TEXT NOT NULL,
    title_en        TEXT NOT NULL,
    node_id         UUID REFERENCES taxonomy_nodes,
    org_unit_id     UUID REFERENCES org_units,
    assigned_to     UUID REFERENCES users,
    status          case_status NOT NULL DEFAULT 'new',
    severity        complaint_severity NOT NULL DEFAULT 'medium',
    sla_due_at      TIMESTAMPTZ,
    first_response_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    complaint_count INT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, reference)
);
CREATE INDEX ix_cases_queue ON cases (tenant_id, status, sla_due_at)
    WHERE status NOT IN ('closed','resolved','rejected');
CREATE INDEX ix_cases_assignee ON cases (assigned_to, status);

ALTER TABLE complaints
    ADD CONSTRAINT fk_complaints_case FOREIGN KEY (case_id) REFERENCES cases;

-- ============================================================
-- RESPONSES (drafts, grounding, approval)
-- ============================================================
CREATE TYPE response_kind AS ENUM
    ('reply','press_release','summary','translation','internal_brief','social_post');
CREATE TYPE response_status AS ENUM
    ('draft','pending_approval','approved','rejected','published','withdrawn');

CREATE TABLE responses (
    response_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    case_id         UUID REFERENCES cases,
    alert_id        UUID,
    kind            response_kind NOT NULL,
    lang            lang_code NOT NULL,
    audience        TEXT,
    body            TEXT NOT NULL,
    body_html       TEXT,
    status          response_status NOT NULL DEFAULT 'draft',
    generated_by_model TEXT,
    model_version   TEXT,
    prompt_version  TEXT,
    inference_run_id UUID,
    retrieval_run_id UUID,
    grounding_score REAL,
    unsupported_claims JSONB NOT NULL DEFAULT '[]',
    policy_flags    JSONB NOT NULL DEFAULT '[]',
    abstained       BOOLEAN NOT NULL DEFAULT FALSE,
    abstain_reason  TEXT,
    created_by      UUID REFERENCES users,
    edited_by       UUID REFERENCES users,
    edit_distance   INT,
    submitted_at    TIMESTAMPTZ,
    approved_by     UUID REFERENCES users,
    approved_at     TIMESTAMPTZ,
    second_approver UUID REFERENCES users,
    rejected_reason TEXT,
    published_at    TIMESTAMPTZ,
    published_ref   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_approval_requires_approver
        CHECK (status <> 'approved' OR approved_by IS NOT NULL),
    CONSTRAINT ck_publish_requires_approval
        CHECK (status <> 'published' OR approved_at IS NOT NULL)
);
CREATE INDEX ix_responses_case ON responses (case_id, created_at DESC);
CREATE INDEX ix_responses_approval_queue
    ON responses (tenant_id, status, submitted_at)
    WHERE status = 'pending_approval';

CREATE TABLE response_citations (
    response_id     UUID NOT NULL REFERENCES responses ON DELETE CASCADE,
    seq             SMALLINT NOT NULL,
    claim_text      TEXT NOT NULL,
    chunk_id        UUID NOT NULL,
    document_id     UUID NOT NULL,
    quoted_text     TEXT NOT NULL,
    start_char      INT,
    end_char        INT,
    entailment      REAL NOT NULL,
    PRIMARY KEY (response_id, seq)
);

-- ============================================================
-- RAG CORPUS
-- ============================================================
CREATE TYPE doc_kind AS ENUM
    ('policy','press_release','faq','tone_of_voice','service_guide','legal','template');

CREATE TABLE documents (
    document_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    kind            doc_kind NOT NULL,
    title_ar        TEXT NOT NULL,
    title_en        TEXT,
    lang            lang_code NOT NULL,
    version         TEXT NOT NULL DEFAULT '1',
    effective_from  DATE,
    effective_to    DATE,
    is_approved     BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by     UUID REFERENCES users,
    object_key      TEXT NOT NULL,
    sha256          BYTEA NOT NULL,
    org_unit_id     UUID REFERENCES org_units,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, object_key, version)
);
-- PostgreSQL forbids CURRENT_DATE in partial-index predicates. Keeping
-- effective_to in the index supports the exact query predicate from section 4.3.
CREATE INDEX ix_documents_retrievable
    ON documents (tenant_id, kind, effective_to) WHERE is_approved;

CREATE TABLE doc_chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    document_id     UUID NOT NULL REFERENCES documents ON DELETE CASCADE,
    seq             INT NOT NULL,
    heading_path    TEXT,
    text            TEXT NOT NULL,
    norm_text       TEXT NOT NULL,
    token_count     INT NOT NULL,
    lang            lang_code NOT NULL,
    embedding       vector(1024) NOT NULL,
    tsv             tsvector,
    UNIQUE (document_id, seq)
);
CREATE INDEX ix_chunks_embedding ON doc_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
CREATE INDEX ix_chunks_tsv ON doc_chunks USING gin (tsv);
CREATE INDEX ix_chunks_trgm ON doc_chunks USING gin (norm_text gin_trgm_ops);
CREATE INDEX ix_chunks_tenant_doc ON doc_chunks (tenant_id, document_id, seq);

-- ============================================================
-- ALERTS & PLAYBOOKS
-- ============================================================
CREATE TYPE alert_tier AS ENUM ('watch','elevated','high','critical');
CREATE TYPE alert_status AS ENUM
    ('open','acknowledged','actioned','resolved','false_positive');

CREATE TABLE alerts (
    alert_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    topic_id        UUID REFERENCES topics,
    node_id         UUID REFERENCES taxonomy_nodes,
    tier            alert_tier NOT NULL,
    risk_score      REAL NOT NULL,
    drivers         JSONB NOT NULL,
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    title_ar        TEXT NOT NULL,
    title_en        TEXT NOT NULL,
    status          alert_status NOT NULL DEFAULT 'open',
    playbook_id     UUID,
    acknowledged_by UUID REFERENCES users,
    acknowledged_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    outcome_label   TEXT,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_alerts_open ON alerts (tenant_id, tier DESC, created_at DESC)
    WHERE status IN ('open','acknowledged');
CREATE INDEX ix_alerts_topic ON alerts (topic_id, created_at DESC);

CREATE TABLE playbooks (
    playbook_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants,
    code            TEXT NOT NULL,
    title_ar        TEXT NOT NULL,
    title_en        TEXT NOT NULL,
    trigger_tier    alert_tier NOT NULL,
    trigger_node_ids UUID[],
    steps           JSONB NOT NULL,
    template_doc_id UUID REFERENCES documents,
    UNIQUE (tenant_id, code)
);
ALTER TABLE alerts ADD CONSTRAINT fk_alerts_playbook
    FOREIGN KEY (playbook_id) REFERENCES playbooks;

-- ============================================================
-- METRICS
-- ============================================================
CREATE TABLE metric_snapshots (
    tenant_id       UUID NOT NULL,
    metric_code     TEXT NOT NULL,
    dimension       JSONB NOT NULL DEFAULT '{}',
    bucket_start    TIMESTAMPTZ NOT NULL,
    granularity     TEXT NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    sample_n        INT NOT NULL
);
-- PostgreSQL forbids expressions in PRIMARY KEY declarations. This unique
-- expression index implements the exact identity rule specified in section 4.3.
CREATE UNIQUE INDEX ux_metric_snapshots_identity ON metric_snapshots (
    tenant_id,
    metric_code,
    granularity,
    bucket_start,
    md5(dimension::text)
);
CREATE INDEX ix_metrics_lookup
    ON metric_snapshots (tenant_id, metric_code, granularity, bucket_start DESC);

-- ============================================================
-- AI LINEAGE
-- ============================================================
CREATE TABLE ai_inference_log (
    inference_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    task            TEXT NOT NULL,
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    prompt_version  TEXT,
    provider        TEXT NOT NULL,
    input_ref       JSONB NOT NULL,
    input_tokens    INT,
    output_tokens   INT,
    cached_tokens   INT,
    latency_ms      INT,
    cost_usd        NUMERIC(10,6),
    status          TEXT NOT NULL,
    error_code      TEXT,
    langfuse_trace_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_inference_task_time
    ON ai_inference_log (tenant_id, task, created_at DESC);
CREATE INDEX ix_inference_cost ON ai_inference_log (tenant_id, created_at DESC)
    WHERE cost_usd IS NOT NULL;

-- ============================================================
-- AUDIT LOG (append-only, partitioned monthly)
-- ============================================================
CREATE TABLE audit_log (
    audit_id        BIGSERIAL,
    tenant_id       UUID NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_user_id   UUID,
    actor_type      TEXT NOT NULL,
    action          TEXT NOT NULL,
    object_type     TEXT NOT NULL,
    object_id       UUID,
    outcome         TEXT NOT NULL,
    ip_addr         INET,
    user_agent      TEXT,
    before_state    JSONB,
    after_state     JSONB,
    request_id      TEXT,
    prev_hash       BYTEA,
    row_hash        BYTEA NOT NULL,
    PRIMARY KEY (audit_id, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE TABLE audit_log_2026_06 PARTITION OF audit_log
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE audit_log_2026_07 PARTITION OF audit_log
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE audit_log_2026_08 PARTITION OF audit_log
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE audit_log_2026_09 PARTITION OF audit_log
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT;
CREATE INDEX ix_audit_actor
    ON audit_log (tenant_id, actor_user_id, occurred_at DESC);
CREATE INDEX ix_audit_object
    ON audit_log (tenant_id, object_type, object_id, occurred_at DESC);
CREATE INDEX ix_audit_action
    ON audit_log (tenant_id, action, occurred_at DESC);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sawtai_app') THEN
        REVOKE UPDATE, DELETE ON audit_log FROM sawtai_app;
    END IF;
END
$$;
