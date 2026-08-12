# SawtAI

Arabic-first government communication intelligence platform. The authoritative
architecture is [`ARCHITECTURE.md`](./ARCHITECTURE.md); this scaffold implements
the Phase 1 foundation described in sections 3, 4.3, 8.2, and 10.

## Foundation included

- Python 3.12 FastAPI modular-monolith skeleton with module boundaries matching
  the architecture.
- ARQ worker process sharing the API image.
- React 19 + Vite TypeScript shell with Arabic RTL as the default.
- PostgreSQL 16 + pgvector, Redis 7, MinIO, Caddy, encoder, and sovereign-LLM
  Compose services. GPU services are opt-in profiles.
- Alembic migration for the complete section 4.3 schema.

## Local startup

On macOS, start Docker Desktop or Colima first:

```sh
colima start --cpu 4 --memory 8 --disk 20
```

```sh
cp .env.example .env
make bootstrap
```

Start the local encoder stub with `--profile gpu`; start the vLLM sovereign path
with `--profile sovereign` after setting a supported model and NVIDIA runtime.

Useful endpoints after startup:

- API health: `http://localhost:8080/api/v1/health`
- Web shell: `http://localhost:8080/`
- MinIO console: `http://localhost:9001/`

The prototype uses Argon2id passwords, 30-minute HS256 access tokens, rotating
HTTP-only refresh sessions, and tenant-scoped role permissions. Demo accounts
all use the password `SawtAI-2026!`:

- `officer@sawtai.ae` — creates, edits, and submits replies.
- `approver@sawtai.ae` — independently approves and sends replies.
- `crisis@sawtai.ae` — accesses crisis monitoring.
- `admin@sawtai.ae` — manages users and roles without citizen-message access.
- `dpo@sawtai.ae` — accesses audit and governed data views.

## Prototype workflows

- **Overview:** database-backed KPI, sentiment, volume, topic, and alert views.
- **Voice Explorer:** filtered message evidence with model lineage and visible
  PII-redaction markers.
- **Draft Studio:** SSE-streamed Arabic reply generation, approved-source
  citation, claim verification, and an explicit refusal path for unsupported or
  forbidden commitments.
- **Crisis Room:** transparent composite-risk gauge, feature drivers, response
  playbook, and a 108-hour replay timeline.
- **Data Explorer:** read-only, tenant-scoped PostgreSQL table counts and row
  previews with restricted and credential fields intentionally hidden.
- **WhatsApp channel:** signed Meta webhook ingestion, request-boundary PII
  protection, Redis worker processing, grounded response drafts, operator
  submission, independent maker-checker approval, and simulated or live
  outbound delivery. See [`BACKEND-WHATSAPP.md`](./BACKEND-WHATSAPP.md).
- **Case Management:** automatic conversion of WhatsApp complaints into
  taxonomy-routed cases, server-side SLA clocks, assignment, controlled status
  transitions, escalation, internal notes, and append-only history.
- **Notification Center:** role-targeted in-app alerts for assignments, critical
  cases, approaching or breached SLAs, waiting citizens, and maker-checker
  approvals, with durable deduplication and audit-logged read state.
- **Governed Knowledge:** secure PDF, DOCX, text, and Markdown ingestion;
  Arabic/English OCR for scanned PDFs; S3-compatible original-file storage;
  structural chunking; hybrid dense/sparse retrieval with optional reranking;
  independent approval; safe abstention; citation-preserving reindexing; and
  non-destructive retirement. The default local encoder is deterministic for
  development, while the optional encoder service uses BGE-M3 and BGE Reranker.

All visible citizen records are deterministic synthetic replay data. The UI and
API label that provenance explicitly; no live social feed or real citizen data
is implied.

Run `make smoke` for public-route checks, `make test` for backend tests, and
`make lint` for Ruff, mypy, and import-boundary validation.

### Development quality gates

- `make test` runs fast backend unit and API-contract tests.
- `make test-integration` validates all prototype routes against the seeded PostgreSQL stack.
- `make lint` runs Ruff, strict mypy, and domain import-boundary checks.
- `npm --prefix services/web test` runs frontend unit tests.
- `npm --prefix services/web run check` type-checks, tests, and builds the frontend.
- `make check` validates Compose, backend quality gates, and production container builds.

The frontend is organised by feature under `services/web/src/features`; reusable API,
component, application, and localisation code lives in sibling top-level directories.
Backend domain packages remain independent and access authentication, auditing, database,
and configuration as shared platform capabilities.

For local pgAdmin access, register `127.0.0.1:5433` with database and user
`sawtai`; the development password is defined in `.env.example`. The port is
bound to localhost only.

## Streamlit annotation tool

The architecture intentionally limits Streamlit to internal annotation and
adjudication. Start it locally with:

```sh
docker compose --profile tools up -d --build annotation
```

Open `http://localhost:8501`. For Streamlit Community Cloud, deploy
`services/annotation/app.py`, install `services/annotation/requirements.txt`,
and set `SAWTAI_API_URL` to the public HTTPS URL of the deployed SawtAI API.

## Public prototype

`render.yaml` deploys the React console and FastAPI API with a background worker,
managed PostgreSQL, and managed Redis. The web container applies the authoritative
schema migration and loads deterministic synthetic demo data before startup.
This topology is for stakeholder review; the complete local Compose topology
remains the reference implementation for all infrastructure services.

## Schema fidelity

The migration preserves all section 4.3 entities, fields, types, constraints,
indexes, and stated prototype partitions. Three syntax-level accommodations are
documented next to the SQL because the illustrative DDL is not directly accepted
by PostgreSQL 16:

1. `citext` is enabled because the schema uses `CITEXT` for user email.
2. The two expression-based primary keys are implemented as equivalent unique
   expression indexes (PostgreSQL does not permit expressions in a primary key).
3. The approved-document index includes `effective_to` and is partial on
   `is_approved`; `CURRENT_DATE` remains a query predicate because volatile dates
   are forbidden in partial-index predicates.

These accommodations do not change the logical data model.
