"""Jooble job search API (many countries, including South Africa).

A free key is requested with the form at https://jooble.org/api/about. Each search
is one POST to https://<host>/api/<key>; the key is part of the URL, so errors from
here are reported without it (see search.describe_error).
"""

from __future__ import annotations

import httpx

from job_hunter.jobs import Job, html_to_text


def search(
    client: httpx.Client,
    *,
    api_key: str,
    keywords: str,
    location: str = "South Africa",
    host: str = "jooble.org",
    results: int = 50,
) -> list[Job]:
    body = {"keywords": keywords, "location": location, "page": "1", "ResultOnPage": str(results)}
    response = client.post(f"https://{host}/api/{api_key}", json=body)
    response.raise_for_status()
    return [_to_job(item) for item in response.json().get("jobs", []) or []]


def _to_job(item: dict) -> Job:
    return Job(
        id=f"jooble:{item.get('id')}",
        source="jooble",
        title=html_to_text(str(item.get("title", ""))),
        company=str(item.get("company", "") or ""),
        location=str(item.get("location", "") or ""),
        url=str(item.get("link", "") or ""),
        description=html_to_text(str(item.get("snippet", "") or "")),
        posted=str(item.get("updated", "") or "")[:10],
        salary=str(item.get("salary", "") or ""),
        extra={"type": item.get("type", ""), "via": item.get("source", ""), "description_is_snippet": True},
    )
