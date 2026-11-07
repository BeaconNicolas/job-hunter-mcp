"""Score how well a job fits the CV, and explain the score."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from job_hunter.config import SearchSettings
from job_hunter.vocabulary import find_terms

# "5+ years", "3-5 years", "at least 4 years", "minimum of 6 yrs"
_YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|to|–)?\s*(?:\d{1,2})?\s*\+?\s*(?:years?|yrs)", re.IGNORECASE
)

# Words in a title that say the job is in the right area even when it is not an exact target title.
_AREA_WORDS = (
    "cloud",
    "devops",
    "platform",
    "infrastructure",
    "aws",
    "terraform",
    "sre",
    "reliability",
    "mlops",
)


@dataclass
class Match:
    score: int
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    title_fit: str = "none"  # "target", "area" or "none"
    required_years: int | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def excluded(title: str, settings: SearchSettings) -> bool:
    lowered = title.lower()
    return any(word in lowered for word in settings.exclude_title_words)


def required_years(text: str) -> int | None:
    """Smallest 'N years' figure mentioned near 'experience', if any."""
    found = []
    for m in _YEARS.finditer(text or ""):
        window = text[max(0, m.start() - 80) : m.end() + 80].lower()
        if "experience" in window:
            found.append(int(m.group(1)))
    plausible = [n for n in found if 0 < n <= 20]
    return min(plausible) if plausible else None


def score_job(title: str, description: str, have: set[str], settings: SearchSettings) -> Match:
    """0-100. 55% skill coverage (skills the job mentions that the CV has),
    45% title fit, minus 15 when the job asks for clearly more experience."""
    wanted = find_terms(f"{title}\n{description}")
    matched = sorted(wanted & have)
    missing = sorted(wanted - have)
    coverage = len(matched) / len(wanted) if wanted else 0.3

    lowered = title.lower()
    if any(t in lowered for t in settings.target_titles):
        title_fit, title_score = "target", 1.0
    elif any(w in lowered for w in _AREA_WORDS):
        title_fit, title_score = "area", 0.5
    else:
        title_fit, title_score = "none", 0.0

    score = 100 * (0.55 * coverage + 0.45 * title_score)
    notes: list[str] = []
    years = required_years(description)
    if years is not None and years > settings.experience_years + 1:
        score -= 15
        notes.append(f"Asks for {years}+ years of experience; you have about {settings.experience_years}.")
    if "senior" in lowered and settings.experience_years < 5:
        notes.append("Senior title: check the experience it expects.")
    if missing:
        notes.append("Not in your CV: " + ", ".join(missing[:8]) + ("..." if len(missing) > 8 else ""))

    return Match(
        score=max(0, min(100, round(score))),
        matched=matched,
        missing=missing,
        title_fit=title_fit,
        required_years=years,
        notes=notes,
    )
