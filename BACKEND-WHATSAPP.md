# SawtAI WhatsApp Backend

## Current capability

The backend implements the complete safe text-message path:

```text
Citizen WhatsApp message
  → Meta webhook verification (GET)
  → HMAC-SHA256 request verification (POST)
  → request-boundary PII redaction and sender pseudonymization
  → encrypted sender mapping in restricted.pii_vault
  → core.messages persistence and exact retry deduplication
  → internal-ID-only ARQ job in Redis
  → approved-document retrieval and grounding gate
  → prompt-injection screening
  → draft response + inference lineage + citation
  → operator inbox
  → explicit approval-and-send
  → Meta Cloud API delivery or local simulation
  → delivery-status audit events
```

No unredacted citizen text or native WhatsApp identifier is placed in the ARQ job payload. The worker receives only `message_id` and `occurred_at`. The native sender identifier is encrypted with `pgcrypto` in the restricted schema and decrypted only at the outbound delivery boundary.

## Safety modes

`WHATSAPP_REPLY_MODE` controls behavior:

- `off`: ingest only.
- `draft`: create a grounded draft; a user must call approval-and-send.
- `acknowledge`: send a fixed, non-generative receipt immediately and also create a grounded draft.

Generative drafts never send automatically. This preserves ADR-009 and the database approval constraint. A future automatic-answer policy must define allowed intents, confidence thresholds, escalation rules, legal approval, and an accountable policy owner before a new mode is added.

`WHATSAPP_DELIVERY_MODE` controls delivery:

- `simulate`: returns a `simulated:<uuid>` delivery reference and exercises the full database workflow.
- `live`: sends through the Meta Graph API and requires a permanent or system-user access token and phone-number ID.

## Configuration

Copy `.env.example` to `.env`, then set:

```dotenv
PII_ENCRYPTION_KEY=<32+ random bytes>
WHATSAPP_VERIFY_TOKEN=<random webhook verification token>
WHATSAPP_APP_SECRET=<Meta app secret>
WHATSAPP_ACCESS_TOKEN=<Meta system-user access token>
WHATSAPP_PHONE_NUMBER_ID=<WhatsApp Business phone number id>
WHATSAPP_SIGNATURE_REQUIRED=true
WHATSAPP_DELIVERY_MODE=simulate
WHATSAPP_REPLY_MODE=draft
WHATSAPP_TENANT_CODE=shj-demo
WHATSAPP_SOURCE_HANDLE=demo-whatsapp
RAG_LEXICAL_GATE=0.18
```

Use different values per environment. Never place real credentials in Git or screenshots. Rotate the access token and app secret immediately if either is exposed.

On Render, `PII_ENCRYPTION_KEY`, `WHATSAPP_ACCESS_TOKEN`, and `WHATSAPP_PHONE_NUMBER_ID` appear on both the web and worker services. Enter the **same values** on both services. The Blueprint deliberately leaves delivery in `simulate` mode until this is verified.

## Meta setup

1. Create or select a Meta app and add the WhatsApp product.
2. Create a WhatsApp Business Account and register a phone number.
3. Configure this callback URL:

   ```text
   https://<public-host>/api/v1/channels/whatsapp/webhook
   ```

4. Use `WHATSAPP_VERIFY_TOKEN` as the webhook verify token.
5. Subscribe to `messages` so inbound messages and delivery statuses reach SawtAI.
6. Set `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, and `WHATSAPP_PHONE_NUMBER_ID` in the deployment secret manager.
7. Keep `WHATSAPP_DELIVERY_MODE=simulate` until verification, privacy, retention, and Arabic reply acceptance tests pass.
8. Change to `live`, send a test message, approve its draft, and confirm `sent`, `delivered`, and `read` audit events.

## API operations

### Verify configuration

```sh
curl -H 'Authorization: Bearer sawtai-demo-token' \
  https://<host>/api/v1/channels/whatsapp/status
```

### Review the inbox

```sh
curl -H 'Authorization: Bearer sawtai-demo-token' \
  'https://<host>/api/v1/channels/whatsapp/inbox?limit=50'
```

The inbox returns redacted text, draft body, grounding score, policy flags, abstention reason, and response status. It never returns the native WhatsApp identifier.

### Approve and send

```sh
curl -X POST \
  -H 'Authorization: Bearer sawtai-demo-token' \
  -H 'Content-Type: application/json' \
  -d '{"comment":"Approved after source review"}' \
  https://<host>/api/v1/channels/whatsapp/replies/<response-id>/approve-and-send
```

The operation is idempotent after publication. It rejects abstained, ungrounded, flagged, missing, or invalid-state drafts.

## Voice path

Audio webhook payloads are recognized but intentionally return `awaiting_audio_processing`; they are not discarded or falsely transcribed. Provider-neutral contracts are defined in `sawtai.nlp.service`:

- `SpeechToTextProvider.transcribe(audio, mime_type) → Transcript`
- `TextToSpeechProvider.synthesize(text, language) → SynthesizedSpeech`

The future path is:

```text
WhatsApp audio media ID
  → authenticated media metadata lookup
  → encrypted object storage
  → sovereign Arabic STT
  → the same redaction, grounding, approval, and reply pipeline
  → optional sovereign Arabic TTS
  → WhatsApp media upload and audio send
```

Provider selection remains open until Arabic dialect targets, hosting/residency, acceptable latency, supported audio formats, voice identity, and consent requirements are specified.

## Local verification

```sh
make bootstrap
make lint
make test
make test-integration
```

The integration suite exercises message persistence, encrypted sender recovery, approved-document retrieval, draft creation, human approval, and simulated WhatsApp delivery against real PostgreSQL.

## Production checklist

- Replace prototype authentication with OIDC/MFA and separate `draft:approve` permission.
- Use a managed Redis/Valkey instance with encryption, authentication, and persistence policy.
- Store Meta credentials and `PII_ENCRYPTION_KEY` in the platform secret manager.
- Configure ingress request limits, Meta IP/replay monitoring, and endpoint rate limiting.
- Archive original payloads in the restricted object bucket before normalization.
- Add dead-letter handling and alerts for repeatedly failed jobs.
- Add per-tenant outbound quotas and Meta template-message handling outside the 24-hour service window.
- Add explicit consent, retention, erasure, and DPIA decisions for WhatsApp identifiers and voice.
- Replace the local grounded-template provider with the approved sovereign generation provider, then run Arabic faithfulness and refusal evaluations.
- Run load tests for webhook bursts and provider rate limits before enabling live traffic.
