"""Paths and settings. Secrets come from environment variables only."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# The repository root (src/job_hunter/config.py -> repo). Override with JOB_HUNTER_HOME.
ROOT = Path(os.environ.get("JOB_HUNTER_HOME") or Path(__file__).resolve().parents[2])


def profile_dir() -> Path:
    return ROOT / "profile"


def output_dir() -> Path:
    return Path(os.environ.get("JOB_HUNTER_OUTPUT") or ROOT / "output")


def state_file() -> Path:
    return Path(os.environ.get("JOB_HUNTER_STATE") or ROOT / "state" / "seen_jobs.json")


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_cv(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or profile_dir() / "cv.yaml")


@dataclass
class SearchSettings:
    target_titles: list[str] = field(default_factory=list)
    exclude_title_words: list[str] = field(default_factory=list)
    experience_years: int = 3
    min_score: int = 55
    max_alerts: int = 5
    adzuna_country: str = "za"
    adzuna_where: str = ""
    adzuna_queries: list[str] = field(default_factory=list)
    adzuna_max_days_old: int = 3
    remotive_categories: list[str] = field(default_factory=list)
    remotive_searches: list[str] = field(default_factory=list)
    remotive_allowed_locations: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> SearchSettings:
        data = load_yaml(path or profile_dir() / "search.yaml")
        adzuna = data.get("adzuna", {})
        remotive = data.get("remotive", {})
        return cls(
            target_titles=[t.lower() for t in data.get("target_titles", [])],
            exclude_title_words=[w.lower() for w in data.get("exclude_title_words", [])],
            experience_years=int(data.get("experience_years", 3)),
            min_score=int(data.get("min_score", 55)),
            max_alerts=int(data.get("max_alerts", 5)),
            adzuna_country=adzuna.get("country", "za"),
            adzuna_where=adzuna.get("where", ""),
            adzuna_queries=list(adzuna.get("queries", [])),
            adzuna_max_days_old=int(adzuna.get("max_days_old", 3)),
            remotive_categories=list(remotive.get("categories", [])),
            remotive_searches=list(remotive.get("searches", [])),
            remotive_allowed_locations=[x.lower() for x in remotive.get("allowed_locations", [])],
        )


def env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None
