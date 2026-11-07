"""Send WhatsApp messages with Meta's WhatsApp Cloud API.

Two kinds of message:
- template: needed for alerts that WhatsApp sends first (the daily alert). The
  template must be created and approved in WhatsApp Manager (README).
- text: free text, which WhatsApp only delivers within 24 hours of your last
  message to the business number.

Settings come from environment variables; the token is never stored in the repo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from job_hunter.config import env

GRAPH = "https://graph.facebook.com/{version}/{phone_number_id}/messages"

# Meta error codes worth a plain explanation.
_HINTS = {
    131047: "More than 24 hours have passed since you last messaged the business number, so free text "
    "is not allowed. Send any message to the business number from your phone, or use a template.",
    131026: "The recipient number cannot receive this message. Check WHATSAPP_TO (country code, no +) "
    "and, in test mode, that the number is in the app's allowed recipient list.",
    132001: "The template name or language does not exist or is not approved yet.",
    132000: "The number of template variables does not match the approved template.",
    132018: "A template variable contains something WhatsApp does not allow (new lines, tabs, many spaces).",
    190: "The access token has expired or is invalid. Create a permanent system-user token (README).",
    10: "The token lacks the whatsapp_business_messaging permission.",
}


class WhatsAppError(RuntimeError):
    pass


@dataclass
class WhatsAppConfig:
    token: str
    phone_number_id: str
    to: str
    template: str | None = None
    template_language: str = "en"
    api_version: str = "v23.0"

    @classmethod
    def from_env(cls) -> WhatsAppConfig | None:
        token, phone_id, to = env("WHATSAPP_TOKEN"), env("WHATSAPP_PHONE_NUMBER_ID"), env("WHATSAPP_TO")
        if not (token and phone_id and to):
            return None
        return cls(
            token=token,
            phone_number_id=phone_id,
            to=re.sub(r"[^\d]", "", to),
            template=env("WHATSAPP_TEMPLATE"),
            template_language=env("WHATSAPP_TEMPLATE_LANG") or "en",
            api_version=env("WHATSAPP_API_VERSION") or "v23.0",
        )


def template_param(text: str, limit: int = 1000) -> str:
    """WhatsApp rejects template variables with new lines, tabs or 4+ spaces in a row."""
    flat = re.sub(r"\s*[\r\n\t]+\s*", " | ", text.strip())
    flat = re.sub(r" {4,}", "   ", flat)
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."


def template_payload(cfg: WhatsAppConfig, params: list[str]) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": cfg.to,
        "type": "template",
        "template": {
            "name": cfg.template,
            "language": {"code": cfg.template_language},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": template_param(p)} for p in params]}
            ],
        },
    }


def text_payload(cfg: WhatsAppConfig, text: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": cfg.to,
        "type": "text",
        "text": {"preview_url": False, "body": text[:4096]},
    }


def send(client: httpx.Client, cfg: WhatsAppConfig, payload: dict) -> str:
    """Send and return the WhatsApp message id; raise WhatsAppError with a hint on failure."""
    response = client.post(
        GRAPH.format(version=cfg.api_version, phone_number_id=cfg.phone_number_id),
        headers={"Authorization": f"Bearer {cfg.token}"},
        json=payload,
    )
    if response.is_success:
        return response.json().get("messages", [{}])[0].get("id", "")
    try:
        error = response.json().get("error", {})
    except ValueError:
        error = {}
    code = error.get("code")
    detail = (error.get("error_data") or {}).get("details") or error.get("message") or response.text[:300]
    hint = _HINTS.get(code, "")
    raise WhatsAppError(
        f"WhatsApp API error {code or response.status_code}: {detail}" + (f" {hint}" if hint else "")
    )
