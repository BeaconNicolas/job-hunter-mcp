"""Collect jobs from all sources and rank them against the CV."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import httpx

from job_hunter.config import SearchSettings, env
from job_hunter.jobs import Job, dedupe
from job_hunter.matching import Match, excluded, score_job
from job_hunter.sources import adzuna, remotive

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
            for q in [query] if query else settings.adzuna_queries:
                try:
                    found = adzuna.search(
                        client,
                        app_id=app_id,
                        app_key=app_key,
                        query=q,
                        country=settings.adzuna_country,
                        where=settings.adzuna_where,
                        max_days_old=settings.adzuna_max_days_old,
                    )
                    log(f"Adzuna '{q}': {len(found)} jobs")
                    out.jobs += found
                except httpx.HTTPError as exc:
                    out.errors.append(f"Adzuna '{q}': {exc}")

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
                out.errors.append(f"Remotive {kind} '{value}': {exc}")

    out.jobs = dedupe(out.jobs)
    return out


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
