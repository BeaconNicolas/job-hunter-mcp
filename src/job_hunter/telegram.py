"""Send messages with a Telegram bot (free, no business verification).

Settings come from environment variables:
- TELEGRAM_BOT_TOKEN: from @BotFather when you create the bot (a password: keep it secret)
- TELEGRAM_CHAT_ID: your chat with the bot (README shows how to find it)

The token is part of every request URL, so errors here never include the URL.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from job_hunter.config import env

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LENGTH = 4096


class TelegramError(RuntimeError):
    pass


@dataclass
class TelegramConfig:
    token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> TelegramConfig | None:
        token, chat_id = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
        if not (token and chat_id):
            return None
        return cls(token=token, chat_id=chat_id)


def _hint(status: int, description: str) -> str:
    text = description.lower()
    if status == 401:
        return "The bot token is wrong. Copy it again from @BotFather."
    if "chat not found" in text:
        return "TELEGRAM_CHAT_ID is wrong, or you have not pressed Start in your bot's chat yet."
    if status == 403:
        return "The bot cannot message you: open your bot in Telegram and press Start (or unblock it)."
    if status == 429:
        return "Telegram is rate-limiting the bot; try again in a minute."
    if "can't parse entities" in text:
        return "The message formatting was rejected; it is sent as plain text next time."
    return ""


def send_text(client: httpx.Client, cfg: TelegramConfig, text: str, *, html: bool = False) -> int:
    """Send a message and return its Telegram message id. `html` enables <b>, <a href> etc."""
    payload: dict = {
        "chat_id": cfg.chat_id,
        "text": text[:MAX_LENGTH],
        "link_preview_options": {"is_disabled": True},
    }
    if html:
        payload["parse_mode"] = "HTML"
    try:
        response = client.post(API.format(token=cfg.token, method="sendMessage"), json=payload)
    except httpx.HTTPError as exc:
        raise TelegramError(f"Could not reach Telegram ({type(exc).__name__}).") from None
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.is_success and data.get("ok"):
        return int(data.get("result", {}).get("message_id", 0))
    status = int(data.get("error_code") or response.status_code)
    description = str(data.get("description") or "no description")
    hint = _hint(status, description)
    raise TelegramError(f"Telegram error {status}: {description}." + (f" {hint}" if hint else ""))
