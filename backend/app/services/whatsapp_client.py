import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger("utender.whatsapp")

# Meta error codes that mean "try again later" rather than "this message is
# wrong": 4 (app-level throttling), 80007 (account-level throttling), and
# 130429 (throughput limit). Everything else that is a 4xx is permanent.
TRANSIENT_META_CODES = frozenset({4, 80007, 130429})

DEFAULT_TIMEOUT_SECONDS = 10.0


class WhatsAppSendError(Exception):
    """A send that did not succeed.

    `transient` tells the outbox whether a retry may succeed. Message content
    is never included in the exception text, only the status and Meta's error
    code.
    """

    def __init__(self, message: str, *, transient: bool, status_code: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.transient = transient
        self.status_code = status_code
        self.error_code = error_code


def mask_recipient(wa_id: str) -> str:
    """Keep only the last four digits, enough to correlate a log line without storing the number."""
    return f"***{wa_id[-4:]}" if len(wa_id) > 4 else "***"


class WhatsAppCloudClient:
    """Thin client for the Cloud API's messages endpoint.

    The transport is injectable so tests can use httpx.MockTransport. In
    production it is the default network transport.
    """

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        api_version: str,
        api_url: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._endpoint = f"{api_url.rstrip('/')}/{api_version}/{phone_number_id}/messages"
        self._client = httpx.Client(timeout=timeout, transport=transport)

    @classmethod
    def from_settings(cls, settings: Settings, transport: httpx.BaseTransport | None = None) -> "WhatsAppCloudClient":
        if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
            raise WhatsAppSendError("WhatsApp is not configured.", transient=False)
        return cls(
            access_token=settings.whatsapp_access_token,
            phone_number_id=settings.whatsapp_phone_number_id,
            api_version=settings.whatsapp_api_version,
            api_url=settings.whatsapp_api_url,
            transport=transport,
        )

    def send_text(self, to_wa_id: str, body: str) -> str:
        return self._send(
            to_wa_id,
            {"type": "text", "text": {"body": body, "preview_url": False}},
        )

    def send_template(
        self,
        to_wa_id: str,
        template_name: str,
        language_code: str,
        components: list[dict[str, Any]] | None = None,
    ) -> str:
        template: dict[str, Any] = {"name": template_name, "language": {"code": language_code}}
        if components:
            template["components"] = components
        return self._send(to_wa_id, {"type": "template", "template": template})

    def send_flow(
        self,
        to_wa_id: str,
        *,
        flow_id: str,
        flow_token: str,
        screen: str,
        body: str,
        cta: str,
        header: str | None = None,
    ) -> str:
        """Send an interactive Flow message that opens on `screen`.

        The flow_token is what ties later data-endpoint requests back to a
        U-Tender session, since Meta doesn't send the sender's number with them.
        Flow messages are only allowed inside the 24-hour window, which a
        customer opens by messaging us first.
        """
        interactive: dict[str, Any] = {
            "type": "flow",
            "body": {"text": body},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_token": flow_token,
                    "flow_id": flow_id,
                    "flow_cta": cta,
                    "flow_action": "navigate",
                    "flow_action_payload": {"screen": screen},
                },
            },
        }
        if header:
            interactive["header"] = {"type": "text", "text": header}
        return self._send(to_wa_id, {"type": "interactive", "interactive": interactive})

    def send_cta_url(self, to_wa_id: str, *, body: str, display_text: str, url: str) -> str:
        """An interactive message with one button that opens `url`. Used for document upload links."""
        return self._send(
            to_wa_id,
            {
                "type": "interactive",
                "interactive": {
                    "type": "cta_url",
                    "body": {"text": body},
                    "action": {"name": "cta_url", "parameters": {"display_text": display_text, "url": url}},
                },
            },
        )

    def send_buttons(self, to_wa_id: str, *, body: str, buttons: list[dict[str, str]]) -> str:
        """An interactive message with up to three reply buttons. Each button tap comes back as a button_reply."""
        return self._send(
            to_wa_id,
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": button["id"], "title": button["title"]}}
                            for button in buttons
                        ]
                    },
                },
            },
        )

    def _send(self, to_wa_id: str, body: dict[str, Any]) -> str:
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to_wa_id, **body}
        try:
            response = self._client.post(
                self._endpoint,
                headers={"Authorization": f"Bearer {self._access_token}"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.warning("WhatsApp send failed before a response (%s) to %s", type(exc).__name__, mask_recipient(to_wa_id))
            raise WhatsAppSendError("Network error talking to WhatsApp.", transient=True) from exc

        error_code = None
        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code == 200:
            messages = data.get("messages") if isinstance(data, dict) else None
            if messages and isinstance(messages[0], dict) and messages[0].get("id"):
                return str(messages[0]["id"])
            raise WhatsAppSendError("WhatsApp accepted the request without a message id.", transient=True, status_code=200)

        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            raw_code = data["error"].get("code")
            if raw_code is not None:
                error_code = str(raw_code)

        transient = response.status_code == 429 or response.status_code >= 500 or (
            error_code is not None and error_code.isdigit() and int(error_code) in TRANSIENT_META_CODES
        )
        logger.warning(
            "WhatsApp send rejected: status=%s code=%s transient=%s to=%s",
            response.status_code,
            error_code,
            transient,
            mask_recipient(to_wa_id),
        )
        raise WhatsAppSendError(
            "WhatsApp rejected the message.",
            transient=transient,
            status_code=response.status_code,
            error_code=error_code,
        )

    def close(self) -> None:
        self._client.close()
