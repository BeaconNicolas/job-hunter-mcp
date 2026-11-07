"""Remotive remote-jobs API. No key needed; Remotive asks for only a few calls a day
and a link back to the job on Remotive, which every result keeps."""

from __future__ import annotations

import httpx

from job_hunter.jobs import Job, html_to_text

API = "https://remotive.com/api/remote-jobs"


def search(
    client: httpx.Client,
    *,
    search: str = "",
    category: str = "",
    allowed_locations: list[str] | None = None,
    limit: int = 100,
) -> list[Job]:
    params: dict[str, str | int] = {"limit": limit}
    if search:
        params["search"] = search
    if category:
        params["category"] = category
    response = client.get(API, params=params)
    response.raise_for_status()
    jobs = [_to_job(item) for item in response.json().get("jobs", [])]
    if allowed_locations:
        jobs = [job for job in jobs if location_allowed(job.location, allowed_locations)]
    return jobs


def location_allowed(location: str, allowed: list[str]) -> bool:
    """True when the job's candidate location mentions an allowed region.
    An empty location is treated as open to everyone."""
    text = (location or "").lower()
    return not text.strip() or any(word in text for word in allowed)


def _to_job(item: dict) -> Job:
    return Job(
        id=f"remotive:{item.get('id')}",
        source="remotive",
        title=item.get("title", ""),
        company=item.get("company_name", ""),
        location=item.get("candidate_required_location", ""),
        url=item.get("url", ""),
        description=html_to_text(item.get("description", "")),
        posted=(item.get("publication_date") or "")[:10],
        salary=item.get("salary", "") or "",
        extra={"job_type": item.get("job_type", ""), "tags": item.get("tags", [])},
    )
