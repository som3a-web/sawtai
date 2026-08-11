from dataclasses import dataclass
from uuid import uuid4

import httpx

from sawtai.config import Settings


class WhatsAppDeliveryError(RuntimeError):
    """Raised when Meta rejects an outbound WhatsApp request."""


@dataclass(frozen=True)
class DeliveryReceipt:
    external_id: str
    simulated: bool


class WhatsAppClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_text(
        self,
        *,
        recipient: str,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> DeliveryReceipt:
        if self.settings.whatsapp_delivery_mode == "simulate":
            return DeliveryReceipt(external_id=f"simulated:{uuid4()}", simulated=True)
        if not self.settings.whatsapp_access_token or not self.settings.whatsapp_phone_number_id:
            raise WhatsAppDeliveryError("Live WhatsApp delivery is not configured")
        payload: dict[str, object] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}
        url = (
            f"{self.settings.whatsapp_graph_base_url.rstrip('/')}"
            f"/{self.settings.whatsapp_graph_version}"
            f"/{self.settings.whatsapp_phone_number_id}/messages"
        )
        headers = {"Authorization": f"Bearer {self.settings.whatsapp_access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.is_error:
            raise WhatsAppDeliveryError(f"Meta delivery failed with status {response.status_code}")
        data = response.json()
        messages = data.get("messages", [])
        if not messages or not messages[0].get("id"):
            raise WhatsAppDeliveryError("Meta delivery response did not contain a message id")
        return DeliveryReceipt(external_id=str(messages[0]["id"]), simulated=False)
