"""Send WhatsApp messages through Cogzi, which owns the shared number and its access token.

U-Tender builds the same Cloud API message bodies as the direct client. This client posts each one,
signed with WHATSAPP_FORWARD_SECRET, to Cogzi's relay. Cogzi sends it from the shared number and
returns the message ID. No Meta token is stored on U-Tender's server.
"""

import hashlib
import hmac
import json
from typing import Any

import httpx

from app.config import Settings
from app.services.whatsapp_client import DEFAULT_TIMEOUT_SECONDS, WhatsAppCloudClient, WhatsAppSendError, mask_recipient


class WhatsAppRelayClient(WhatsAppCloudClient):
    def __init__(
        self,
        *,
        relay_url: str,
        secret: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._relay_url = relay_url
        self._secret = secret
        self._client = httpx.Client(timeout=timeout, transport=transport)

    @classmethod
    def from_settings(cls, settings: Settings, transport: httpx.BaseTransport | None = None) -> "WhatsAppRelayClient":
        if not settings.whatsapp_relay_url or not settings.whatsapp_forward_secret:
            raise WhatsAppSendError("The WhatsApp relay is not configured.", transient=False)
        return cls(relay_url=settings.whatsapp_relay_url, secret=settings.whatsapp_forward_secret, transport=transport)

    def _send(self, to_wa_id: str, body: dict[str, Any]) -> str:
        raw = json.dumps({"to": to_wa_id, "message": body}, ensure_ascii=False).encode()
        signature = "sha256=" + hmac.new(self._secret.encode(), raw, hashlib.sha256).hexdigest()
        try:
            response = self._client.post(
                self._relay_url,
                content=raw,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
            )
        except httpx.HTTPError as exc:
            raise WhatsAppSendError("Network error talking to the WhatsApp relay.", transient=True) from exc

        if response.status_code == 200:
            try:
                message_id = response.json().get("message_id")
            except ValueError:
                message_id = None
            if message_id:
                return str(message_id)
            raise WhatsAppSendError("The relay did not return a message ID.", transient=True)

        transient = response.status_code == 429 or response.status_code >= 500
        raise WhatsAppSendError(
            f"The relay refused a message to {mask_recipient(to_wa_id)}.",
            transient=transient,
            status_code=response.status_code,
        )
