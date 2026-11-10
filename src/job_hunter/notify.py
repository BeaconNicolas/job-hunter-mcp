"""Send job alerts and messages to your phone: Telegram and/or WhatsApp.

Every channel whose settings are present is used. Telegram needs only a bot token
and chat id; WhatsApp needs an unlocked (in practice, verified) Meta business account.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

import httpx

from job_hunter.jobs import Job
from job_hunter.matching import Match
from job_hunter.telegram import TelegramConfig, TelegramError
from job_hunter.telegram import send_text as telegram_send
from job_hunter.whatsapp import WhatsAppConfig, WhatsAppError, template_payload, text_payload
from job_hunter.whatsapp import send as whatsapp_send

TEMPLATE_LISTING_LIMIT = 900  # characters; WhatsApp allows about 1,000 per template variable
SETUP_HINT = "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (README) to get alerts on your phone."


@dataclass
class Delivery:
    sent: list[str] = field(default_factory=list)  # channel names that worked
    errors: list[str] = field(default_factory=list)


def configured() -> list[str]:
    names = []
    if TelegramConfig.from_env():
        names.append("Telegram")
    if WhatsAppConfig.from_env():
        names.append("WhatsApp")
    return names


# ----------------------------------------------------------------- formatting
def _plural(n: int) -> str:
    return f"{n} new job{'s' if n != 1 else ''} that match your CV"


def job_line(n: int, job: Job, match: Match) -> str:
    where = f" ({job.location})" if job.location else ""
    return f"{n}) {job.title} - {job.company}{where}, {match.score}% match: {job.url}"


def template_listing(top: list[tuple[Job, Match]]) -> str:
    """One line per job, cut short to fit in a WhatsApp template variable."""
    lines: list[str] = []
    for n, (job, match) in enumerate(top, start=1):
        line = job_line(n, job, match)
        if len(" ".join(lines + [line])) > TEMPLATE_LISTING_LIMIT:
            lines.append(f"(+{len(top) - n + 1} more: ask Claude to search_jobs)")
            break
        lines.append(line)
    return " ".join(lines)


def plain_message(top: list[tuple[Job, Match]]) -> str:
    """WhatsApp-style text (*bold*), also used for previews in the terminal."""
    parts = [f"*{_plural(len(top))}*"]
    for n, (job, match) in enumerate(top, start=1):
        details = " · ".join(x for x in (job.location, f"{match.score}% match", job.salary) if x)
        parts.append(f"{n}. *{job.title}* - {job.company}\n{details}\n{job.url}")
    parts.append("Ask Claude to tailor your CV for any of these.")
    return "\n\n".join(parts)


def telegram_message(top: list[tuple[Job, Match]]) -> str:
    """Telegram HTML: bold titles and a tappable link per job."""
    e = html.escape
    parts = [f"<b>{_plural(len(top))}</b>"]
    for n, (job, match) in enumerate(top, start=1):
        details = " · ".join(e(x) for x in (job.location, f"{match.score}% match", job.salary) if x)
        link = f'<a href="{e(job.url, quote=True)}">Open the advert</a>' if job.url else ""
        missing = f"\nMissing: {e(', '.join(match.missing[:5]))}" if match.missing else ""
        parts.append(f"{n}. <b>{e(job.title)}</b> - {e(job.company)}\n{details}{missing}\n{link}".rstrip())
    parts.append("Ask Claude to tailor your CV for any of these.")
    return "\n\n".join(parts)


# ----------------------------------------------------------------- sending
def send_jobs(client: httpx.Client, top: list[tuple[Job, Match]]) -> Delivery:
    result = Delivery()
    tg = TelegramConfig.from_env()
    if tg:
        try:
            telegram_send(client, tg, telegram_message(top), html=True)
            result.sent.append("Telegram")
        except TelegramError as exc:
            result.errors.append(f"Telegram: {exc}")
    wa = WhatsAppConfig.from_env()
    if wa:
        try:
            if wa.template:
                payload = template_payload(wa, [str(len(top)), template_listing(top)])
            else:
                payload = text_payload(wa, plain_message(top))
            whatsapp_send(client, wa, payload)
            result.sent.append("WhatsApp")
        except WhatsAppError as exc:
            result.errors.append(f"WhatsApp: {exc}")
    return result


def send_text(client: httpx.Client, text: str) -> Delivery:
    """Free text to every configured channel (WhatsApp only within its 24-hour window)."""
    result = Delivery()
    tg = TelegramConfig.from_env()
    if tg:
        try:
            telegram_send(client, tg, text)
            result.sent.append("Telegram")
        except TelegramError as exc:
            result.errors.append(f"Telegram: {exc}")
    wa = WhatsAppConfig.from_env()
    if wa:
        try:
            whatsapp_send(client, wa, text_payload(wa, text))
            result.sent.append("WhatsApp")
        except WhatsAppError as exc:
            result.errors.append(f"WhatsApp: {exc}")
    return result
