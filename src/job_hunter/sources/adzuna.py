"""Adzuna job search API (covers South Africa). Free key: https://developer.adzuna.com/"""

from __future__ import annotations

import httpx

from job_hunter.jobs import Job, html_to_text

API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def search(
    client: httpx.Client,
    *,
    app_id: str,
    app_key: str,
    query: str,
    country: str = "za",
    where: str = "",
    max_days_old: int = 3,
    results: int = 50,
) -> list[Job]:
    params: dict[str, str | int] = {
        "app_id": app_id,
        "app_key": app_key,
        "what": query,
        "results_per_page": results,
        "max_days_old": max_days_old,
        "sort_by": "date",
        "content-type": "application/json",
    }
    if where:
        params["where"] = where
    response = client.get(API.format(country=country, page=1), params=params)
    response.raise_for_status()
    return [_to_job(item, country) for item in response.json().get("results", [])]


def _to_job(item: dict, country: str) -> Job:
    salary = ""
    if item.get("salary_min") or item.get("salary_max"):
        low, high = item.get("salary_min"), item.get("salary_max")
        currency = "R" if country == "za" else ""
        salary = " - ".join(f"{currency}{int(v):,}" for v in (low, high) if v)
        if item.get("salary_is_predicted") == "1":
            salary += " (estimate)"
    return Job(
        id=f"adzuna:{item.get('id')}",
        source="adzuna",
        title=html_to_text(item.get("title", "")),
        company=(item.get("company") or {}).get("display_name", ""),
        location=(item.get("location") or {}).get("display_name", ""),
        url=item.get("redirect_url", ""),
        description=html_to_text(item.get("description", "")),
        posted=(item.get("created") or "")[:10],
        salary=salary,
        extra={"contract_time": item.get("contract_time", ""), "description_is_snippet": True},
    )
