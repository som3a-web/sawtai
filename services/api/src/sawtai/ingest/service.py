"""Public ingestion-module facade."""

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sawtai.arabic import normalize_for_search

EMAIL = re.compile(r"(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)")
PHONE = re.compile(r"(?<!\d)(?:\+?971|00971|0)?[\s-]?(?:5\d|[2-9])[\s-]?\d{3}[\s-]?\d{4}(?!\d)")
EMIRATES_ID = re.compile(r"(?<!\d)784[\s-]?\d{4}[\s-]?\d{7}[\s-]?\d(?!\d)")
ARABIC_CHARACTER = re.compile(r"[\u0600-\u06FF]")
LATIN_CHARACTER = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class InboundMessage:
    external_id: str
    sender_native_id: str
    occurred_at: datetime
    text: str
    parent_external_id: str | None = None
    phone_number_id: str | None = None
    message_type: str = "text"


@dataclass(frozen=True)
class PersistedMessage:
    message_id: UUID
    tenant_id: UUID
    source_id: UUID
    channel_id: UUID
    occurred_at: datetime
    redacted_text: str
    duplicate: bool


def redact_pii(value: str) -> tuple[str, tuple[str, ...]]:
    findings: list[str] = []

    def replace(pattern: re.Pattern[str], label: str, current: str) -> str:
        index = 0

        def replacement(_: re.Match[str]) -> str:
            nonlocal index
            index += 1
            findings.append(label)
            return f"<{label}_{index}>"

        return pattern.sub(replacement, current)

    redacted = replace(EMIRATES_ID, "EMIRATES_ID", value)
    redacted = replace(EMAIL, "EMAIL", redacted)
    redacted = replace(PHONE, "PHONE", redacted)
    return redacted, tuple(findings)


def pseudonymize_author(native_id: str, *, tenant_code: str, pepper: str) -> str:
    digest = hmac.new(
        pepper.encode(),
        f"{tenant_code}:{native_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]


def identify_language(value: str) -> tuple[str, float]:
    arabic_count = len(ARABIC_CHARACTER.findall(value))
    latin_count = len(LATIN_CHARACTER.findall(value))
    total = arabic_count + latin_count
    if total == 0:
        return "other", 0.0
    ratio = latin_count / total
    if arabic_count and latin_count and min(arabic_count, latin_count) / total >= 0.12:
        return "mixed", ratio
    return ("ar", ratio) if arabic_count >= latin_count else ("en", ratio)


def simhash64(value: str) -> int:
    tokens = [value[index : index + 3] for index in range(max(1, len(value) - 2))]
    vector = [0] * 64
    for token in tokens:
        hashed = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += 1 if hashed & (1 << bit) else -1
    unsigned = sum(1 << bit for bit, score in enumerate(vector) if score >= 0)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


async def persist_inbound_message(
    session: AsyncSession,
    *,
    tenant_code: str,
    source_handle: str,
    tenant_pepper: str,
    pii_encryption_key: str,
    inbound: InboundMessage,
) -> PersistedMessage:
    source = (
        await session.execute(
            text(
                """
                SELECT t.tenant_id, s.source_id, c.channel_id
                FROM core.tenants t
                JOIN core.sources s ON s.tenant_id = t.tenant_id
                JOIN core.channels c ON c.channel_id = s.channel_id
                WHERE t.code = :tenant_code
                  AND s.handle = :source_handle
                  AND c.code = 'whatsapp'
                  AND s.is_enabled
                """
            ),
            {"tenant_code": tenant_code, "source_handle": source_handle},
        )
    ).mappings().one_or_none()
    if source is None:
        raise RuntimeError("The configured WhatsApp source does not exist or is disabled")

    existing = (
        await session.execute(
            text(
                """
                SELECT message_id, occurred_at, raw_text
                FROM core.messages
                WHERE tenant_id = :tenant_id
                  AND source_id = :source_id
                  AND external_id = :external_id
                ORDER BY occurred_at DESC
                LIMIT 1
                """
            ),
            {
                "tenant_id": source["tenant_id"],
                "source_id": source["source_id"],
                "external_id": inbound.external_id,
            },
        )
    ).mappings().one_or_none()
    if existing:
        return PersistedMessage(
            message_id=existing["message_id"],
            tenant_id=source["tenant_id"],
            source_id=source["source_id"],
            channel_id=source["channel_id"],
            occurred_at=existing["occurred_at"],
            redacted_text=existing["raw_text"],
            duplicate=True,
        )

    now = datetime.now(UTC)
    occurred_at = inbound.occurred_at.astimezone(UTC)
    if occurred_at > now + timedelta(minutes=5):
        occurred_at = now
    redacted, _ = redact_pii(inbound.text)
    normalized = normalize_for_search(redacted)
    language, code_switch_ratio = identify_language(redacted)
    pseudonym = pseudonymize_author(
        inbound.sender_native_id,
        tenant_code=tenant_code,
        pepper=tenant_pepper,
    )
    content_hash = hashlib.sha256(f"{source['source_id']}:{normalized}".encode()).digest()
    engagement = {
        "message_type": inbound.message_type,
        "phone_number_id": inbound.phone_number_id,
    }
    inserted = (
        await session.execute(
            text(
                """
                INSERT INTO core.messages (
                    tenant_id, source_id, channel_id, external_id, parent_external_id,
                    occurred_at, author_pseudonym, raw_text, norm_text, lang_primary,
                    code_switch_ratio, dialect, content_hash, simhash, data_tier,
                    engagement, enrichment_state
                ) VALUES (
                    :tenant_id, :source_id, :channel_id, :external_id, :parent_external_id,
                    :occurred_at, :author_pseudonym, :raw_text, :norm_text,
                    CAST(:lang_primary AS core.lang_code), :code_switch_ratio, 'unknown',
                    :content_hash, :simhash, 'c2_personal', CAST(:engagement AS jsonb), 0
                )
                ON CONFLICT (tenant_id, content_hash, occurred_at) DO NOTHING
                RETURNING message_id
                """
            ),
            {
                "tenant_id": source["tenant_id"],
                "source_id": source["source_id"],
                "channel_id": source["channel_id"],
                "external_id": inbound.external_id,
                "parent_external_id": inbound.parent_external_id,
                "occurred_at": occurred_at,
                "author_pseudonym": pseudonym,
                "raw_text": redacted,
                "norm_text": normalized,
                "lang_primary": language,
                "code_switch_ratio": code_switch_ratio,
                "content_hash": content_hash,
                "simhash": simhash64(normalized),
                "engagement": json.dumps(engagement),
            },
        )
    ).scalar_one_or_none()
    if inserted is None:
        duplicate = (
            await session.execute(
                text(
                    """
                    SELECT message_id, raw_text
                    FROM core.messages
                    WHERE tenant_id = :tenant_id
                      AND content_hash = :content_hash
                      AND occurred_at = :occurred_at
                    LIMIT 1
                    """
                ),
                {
                    "tenant_id": source["tenant_id"],
                    "content_hash": content_hash,
                    "occurred_at": occurred_at,
                },
            )
        ).mappings().one()
        return PersistedMessage(
            message_id=duplicate["message_id"],
            tenant_id=source["tenant_id"],
            source_id=source["source_id"],
            channel_id=source["channel_id"],
            occurred_at=occurred_at,
            redacted_text=duplicate["raw_text"],
            duplicate=True,
        )
    await session.execute(
        text(
            """
            INSERT INTO restricted.pii_vault (
                author_pseudonym, tenant_id, native_id_enc, first_seen_at
            ) VALUES (
                :author_pseudonym, :tenant_id,
                pgp_sym_encrypt(:native_id, :encryption_key), now()
            )
            ON CONFLICT (author_pseudonym) DO NOTHING
            """
        ),
        {
            "author_pseudonym": pseudonym,
            "tenant_id": source["tenant_id"],
            "native_id": inbound.sender_native_id,
            "encryption_key": pii_encryption_key,
        },
    )
    return PersistedMessage(
        message_id=inserted,
        tenant_id=source["tenant_id"],
        source_id=source["source_id"],
        channel_id=source["channel_id"],
        occurred_at=occurred_at,
        redacted_text=redacted,
        duplicate=False,
    )
