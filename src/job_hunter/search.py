"""Collect jobs from all sources and rank them against the CV."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import httpx

from job_hunter.config import SearchSettings, env
from job_hunter.jobs import Job, dedupe
from job_hunter.matching import Match, excluded, score_job
from job_hunter.sources import adzuna, jooble, remotive

Where = Literal["south_africa", "remote", "both"]


@dataclass
class Collected:
    jobs: list[Job] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def collect(
    client: httpx.Client,
    settings: SearchSettings,
    *,
    query: str = "",
    where: Where = "both",
    log: Callable[[str], None] = lambda _msg: None,
) -> Collected:
    """Search the sources. With `query`, run just that search; otherwise use search.yaml."""
    out = Collected()

    if where in ("south_africa", "both"):
        app_id, app_key = env("ADZUNA_APP_ID"), env("ADZUNA_APP_KEY")
        if not (app_id and app_key):
            out.notes.append(
                "Adzuna skipped: set ADZUNA_APP_ID and ADZUNA_APP_KEY to search South African jobs."
            )
        else:
            if query:
                searches = [(f"'{query}'", {"query": query})]
            else:
                searches = [
                    (f"any of '{' '.join(settings.adzuna_any_of)}'", {"any_of": settings.adzuna_any_of})
                ]
                searches = searches if settings.adzuna_any_of else []
                searches += [(f"'{q}'", {"query": q}) for q in settings.adzuna_queries]
            for label, terms in searches:
                try:
                    found = adzuna.search(
                        client,
                        app_id=app_id,
                        app_key=app_key,
                        country=settings.adzuna_country,
                        where=settings.adzuna_where,
                        max_days_old=settings.adzuna_max_days_old,
                        **terms,
                    )
                    log(f"Adzuna {label}: {len(found)} jobs")
                    out.jobs += found
                except httpx.HTTPError as exc:
                    out.errors.append(f"Adzuna {label}: {describe_error(exc, 'Adzuna')}")

    if where in ("south_africa", "both"):
        jooble_key = env("JOOBLE_API_KEY")
        if not jooble_key:
            out.notes.append("Jooble skipped: set JOOBLE_API_KEY to search more South African jobs.")
        else:
            for keywords in [query] if query else settings.jooble_keywords:
                try:
                    found = jooble.search(
                        client,
                        api_key=jooble_key,
                        keywords=keywords,
                        location=settings.jooble_location,
                        host=settings.jooble_host,
                    )
                    log(f"Jooble '{keywords}': {len(found)} jobs")
                    out.jobs += found
                except httpx.HTTPError as exc:
                    out.errors.append(f"Jooble '{keywords}': {describe_error(exc, 'Jooble')}")

    if where in ("remote", "both"):
        calls = (
            [("search", query)]
            if query
            else (
                [("category", c) for c in settings.remotive_categories]
                + [("search", s) for s in settings.remotive_searches]
            )
        )
        for kind, value in calls:
            try:
                found = remotive.search(
                    client,
                    allowed_locations=settings.remotive_allowed_locations,
                    **{kind: value},
                )
                log(f"Remotive {kind} '{value}': {len(found)} jobs open to your location")
                out.jobs += found
            except httpx.HTTPError as exc:
                out.errors.append(f"Remotive {kind} '{value}': {describe_error(exc, 'Remotive')}")

    out.jobs = dedupe(out.jobs)
    return out


def describe_error(exc: httpx.HTTPError, source: str) -> str:
    """A short, safe description: never the request URL, which can contain API keys."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        hint = {
            401: f"check the {source} key and ID",
            403: f"{source} refused the request: check the key, or the plan's call limit may be used up",
            429: f"{source} call limit reached",
        }.get(status, "")
        return f"HTTP {status}" + (f" ({hint})" if hint else "")
    return f"{type(exc).__name__} (network problem or timeout)"


def rank(jobs: list[Job], have: set[str], settings: SearchSettings) -> list[tuple[Job, Match]]:
    """Score every job (skipping excluded titles), best first, newest first on ties."""
    scored = [
        (job, score_job(job.title, job.description, have, settings))
        for job in jobs
        if not excluded(job.title, settings)
    ]
    scored.sort(key=lambda pair: (pair[1].score, pair[0].posted), reverse=True)
    return scored


def http_client() -> httpx.Client:
    return httpx.Client(
        timeout=30, headers={"User-Agent": "job-hunter-mcp (personal job search)"}, follow_redirects=True
    )
