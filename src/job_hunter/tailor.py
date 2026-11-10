"""Tailor the CV to one job without inventing anything.

Claude (through the MCP tool) decides what to emphasise; this module applies it
and refuses changes that add facts the master CV does not contain:

- skills must already be in the CV (they may be reordered, regrouped or dropped);
- rewritten bullets, the summary and the headline may only mention technologies
  the CV already mentions, and only numbers the CV already contains;
- ids must exist.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from job_hunter.render import render_docx
from job_hunter.vocabulary import cv_terms, cv_text, find_terms

_NUMBER = re.compile(r"\d[\d,.]*")


# ----------------------------------------------------------------- ids
def annotate(cv: dict) -> dict:
    """Copy of the CV with stable ids: e1 (job), e1.r2 (role), e1.r2.b3 (bullet), p1 (project)."""
    out = copy.deepcopy(cv)
    for i, job in enumerate(out.get("experience", []), start=1):
        job["id"] = f"e{i}"
        for j, role in enumerate(job.get("roles", []), start=1):
            role["id"] = f"e{i}.r{j}"
            bullets = []
            for k, bullet in enumerate(role.get("bullets", []), start=1):
                bullet = bullet if isinstance(bullet, dict) else {"text": str(bullet)}
                bullet["id"] = f"e{i}.r{j}.b{k}"
                bullets.append(bullet)
            role["bullets"] = bullets
    for i, project in enumerate(out.get("projects", []), start=1):
        project["id"] = f"p{i}"
    return out


def bullet_index(cv: dict) -> dict[str, dict]:
    return {
        bullet["id"]: bullet
        for job in cv.get("experience", [])
        for role in job.get("roles", [])
        for bullet in role.get("bullets", [])
    }


# ----------------------------------------------------------------- checks
def _numbers(text: str) -> set[str]:
    return {n.rstrip(".,").replace(",", "").lstrip("0") or "0" for n in _NUMBER.findall(text or "")}


def years_of_experience(cv: dict, today: date | None = None) -> int:
    """Whole years since the earliest start date of the jobs shown by default."""
    today = today or date.today()
    starts = []
    for job in cv.get("experience", []):
        if not job.get("include", True):
            continue
        try:
            year, month = str(job.get("start", "")).split("-")[:2]
            starts.append(date(int(year), int(month), 1))
        except ValueError:
            continue
    if not starts:
        return 0
    first = min(starts)
    return (today.year - first.year) - ((today.month, today.day) < (first.month, first.day))


def check_claims(text: str, allowed_terms: set[str], allowed_numbers: set[str], where: str) -> list[str]:
    problems = []
    new_terms = sorted(find_terms(text) - allowed_terms)
    if new_terms:
        problems.append(f"{where}: mentions {', '.join(new_terms)}, which your CV does not.")
    new_numbers = sorted(_numbers(text) - allowed_numbers)
    if new_numbers:
        problems.append(f"{where}: uses the number(s) {', '.join(new_numbers)}, which your CV does not contain.")
    return problems


# ----------------------------------------------------------------- request
@dataclass
class TailorRequest:
    job_title: str
    company: str
    summary: str | None = None
    headline: str | None = None
    skills: list[dict[str, Any]] | None = None  # [{"group": "...", "items": [...]}]
    bullet_order: list[str] = field(default_factory=list)  # ids shown first, in this order, within their role
    hide_bullets: list[str] = field(default_factory=list)
    rewrites: dict[str, str] = field(default_factory=dict)  # bullet id -> reworded text
    projects: list[str] | None = None  # project ids to show, in order
    show_experience: list[str] = field(default_factory=list)  # job ids hidden by default to show
    hide_experience: list[str] = field(default_factory=list)


@dataclass
class TailorResult:
    ok: bool
    problems: list[str]
    changes: list[str]
    cv: dict | None = None
    docx_path: str | None = None
    yaml_path: str | None = None


def apply(master: dict, req: TailorRequest, today: date | None = None) -> TailorResult:
    cv = annotate(master)
    have = cv_terms(master)
    master_numbers = _numbers(cv_text(master)) | {str(years_of_experience(master, today))}
    bullets = bullet_index(cv)
    job_ids = {job["id"] for job in cv.get("experience", [])}
    project_ids = [p["id"] for p in cv.get("projects", [])]
    problems: list[str] = []
    changes: list[str] = []

    # Ids must exist.
    for name, ids, known in (
        ("bullet_order", req.bullet_order, bullets),
        ("hide_bullets", req.hide_bullets, bullets),
        ("rewrites", list(req.rewrites), bullets),
        ("projects", req.projects or [], project_ids),
        ("show_experience", req.show_experience, job_ids),
        ("hide_experience", req.hide_experience, job_ids),
    ):
        unknown = [i for i in ids if i not in known]
        if unknown:
            problems.append(f"{name}: unknown id(s) {', '.join(unknown)}. Call get_cv to see the ids.")

    # Free text may only use the CV's own technologies and numbers.
    if req.summary is not None:
        problems += check_claims(req.summary, have, master_numbers, "summary")
    if req.headline is not None:
        problems += check_claims(req.headline, have, master_numbers, "headline")
    for bullet_id, text in req.rewrites.items():
        if bullet_id in bullets:
            original = bullets[bullet_id]["text"]
            problems += check_claims(text, have, _numbers(original), f"rewrite of {bullet_id}")

    # Skills: only items that already exist in the CV.
    existing_skills = {str(item).lower(): str(item) for g in master.get("skills", []) for item in g.get("items", [])}
    if req.skills is not None:
        for group in req.skills:
            for item in group.get("items", []):
                if str(item).lower() not in existing_skills:
                    problems.append(f"skills: '{item}' is not a skill in your CV.")

    if problems:
        return TailorResult(ok=False, problems=problems, changes=[])

    # Apply.
    if req.headline is not None:
        cv["basics"]["headline"] = req.headline
        changes.append("New headline.")
    if req.summary is not None:
        cv["summary"] = req.summary
        changes.append("New profile summary.")
    if req.skills is not None:
        cv["skills"] = [
            {"group": g["group"], "items": [existing_skills[str(i).lower()] for i in g.get("items", [])]}
            for g in req.skills
            if g.get("items")
        ]
        changes.append("Skills reordered for this job.")
    for bullet_id, text in req.rewrites.items():
        bullets[bullet_id]["text"] = text
        changes.append(f"Reworded {bullet_id}.")

    order = {bullet_id: n for n, bullet_id in enumerate(req.bullet_order)}
    hidden = set(req.hide_bullets)
    for job in cv.get("experience", []):
        if job["id"] in req.show_experience:
            job["include"] = True
            changes.append(f"Showing {job['id']} ({job['org']}).")
        if job["id"] in req.hide_experience:
            job["include"] = False
            changes.append(f"Hiding {job['id']} ({job['org']}).")
        for role in job.get("roles", []):
            kept = [b for b in role["bullets"] if b["id"] not in hidden]
            kept.sort(key=lambda b: (order.get(b["id"], len(order)), b["id"]))
            role["bullets"] = kept
    if req.bullet_order:
        changes.append("Most relevant bullets moved to the top of each role.")
    if hidden:
        changes.append(f"Hid {len(hidden)} less relevant bullet(s).")

    if req.projects is not None:
        by_id = {p["id"]: p for p in cv.get("projects", [])}
        chosen = [dict(by_id[i], include=True) for i in req.projects]
        cv["projects"] = chosen
        changes.append("Projects chosen for this job: " + ", ".join(p["name"] for p in chosen) + ".")

    return TailorResult(ok=True, problems=[], changes=changes, cv=cv)


def slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "job"


def save(
    result: TailorResult, req: TailorRequest, output_dir: Path, name: str, today: date | None = None
) -> TailorResult:
    """Write the tailored CV as Word (.docx) and as YAML (a record of exactly what was sent)."""
    assert result.ok and result.cv is not None
    stamp = (today or date.today()).isoformat()
    base = output_dir / "tailored" / f"{stamp}_{slug(req.company)}_{slug(req.job_title)}"
    base.parent.mkdir(parents=True, exist_ok=True)
    docx_path = base.parent / f"{base.name}_{slug(name, 30)}_CV.docx"
    render_docx(result.cv, docx_path)
    yaml_path = base.with_suffix(".yaml")
    with open(yaml_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(
            {
                "job": {"title": req.job_title, "company": req.company},
                "changes": result.changes,
                "cv": result.cv,
            },
            handle,
            sort_keys=False,
            allow_unicode=True,
        )
    result.docx_path, result.yaml_path = str(docx_path), str(yaml_path)
    return result
