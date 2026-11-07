"""The job record shared by all sources, and small text helpers."""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Job:
    id: str  # "<source>:<source id>", unique across sources
    source: str
    title: str
    company: str
    location: str
    url: str
    description: str  # plain text
    posted: str = ""  # ISO date when known
    salary: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr)[^>]*>", re.IGNORECASE)
_SPACES = re.compile(r"[ \t\r\f\v]+")


def html_to_text(raw: str) -> str:
    """Rough HTML to plain text: keeps line breaks between blocks, drops tags."""
    text = _BLOCK.sub("\n", raw or "")
    text = html.unescape(_TAG.sub(" ", text))
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def dedupe(jobs: list[Job]) -> list[Job]:
    """Drop repeats: same id, or same title and company from different queries."""
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    unique: list[Job] = []
    for job in jobs:
        key = (job.title.strip().lower(), job.company.strip().lower())
        if job.id in seen_ids or key in seen_keys:
            continue
        seen_ids.add(job.id)
        seen_keys.add(key)
        unique.append(job)
    return unique
