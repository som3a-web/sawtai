from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WhatsAppText(BaseModel):
    body: str


class WhatsAppMedia(BaseModel):
    id: str
    mime_type: str | None = None
    sha256: str | None = None


class WhatsAppMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str = Field(alias="id")
    sender: str = Field(alias="from")
    timestamp: str
    type: str
    text: WhatsAppText | None = None
    audio: WhatsAppMedia | None = None
    image: WhatsAppMedia | None = None
    document: WhatsAppMedia | None = None

    @property
    def occurred_at(self) -> datetime:
        try:
            return datetime.fromtimestamp(int(self.timestamp), tz=UTC)
        except (ValueError, OSError):
            return datetime.now(UTC)

    @property
    def textual_content(self) -> str | None:
        if self.type == "text" and self.text:
            return self.text.body.strip()
        return None


class WhatsAppStatus(BaseModel):
    id: str
    status: str
    timestamp: str
    recipient_id: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class WhatsAppMetadata(BaseModel):
    display_phone_number: str | None = None
    phone_number_id: str | None = None


class WhatsAppValue(BaseModel):
    messaging_product: str | None = None
    metadata: WhatsAppMetadata = Field(default_factory=WhatsAppMetadata)
    messages: list[WhatsAppMessage] = Field(default_factory=list)
    statuses: list[WhatsAppStatus] = Field(default_factory=list)


class WhatsAppChange(BaseModel):
    field: str
    value: WhatsAppValue


class WhatsAppEntry(BaseModel):
    id: str
    changes: list[WhatsAppChange] = Field(default_factory=list)


class WhatsAppWebhook(BaseModel):
    object: str
    entry: list[WhatsAppEntry] = Field(default_factory=list)

    def events(self) -> tuple[list[tuple[WhatsAppMessage, WhatsAppMetadata]], list[WhatsAppStatus]]:
        messages: list[tuple[WhatsAppMessage, WhatsAppMetadata]] = []
        statuses: list[WhatsAppStatus] = []
        for entry in self.entry:
            for change in entry.changes:
                messages.extend((message, change.value.metadata) for message in change.value.messages)
                statuses.extend(change.value.statuses)
        return messages, statuses


class ReplyApprovalRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=500)


class ReplyUpdateRequest(BaseModel):
    body: str = Field(min_length=10, max_length=4000)
