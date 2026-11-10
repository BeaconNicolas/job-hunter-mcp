"""MCP server: search jobs that fit the CV, explain the fit, and tailor the CV.

Claude Desktop starts it with `uv --directory <repo> run job-hunter-mcp` (README).
"""

from __future__ import annotations

from typing import Any, Literal

import yaml
from mcp.server.mcpserver import MCPServer

from job_hunter import config, notify
from job_hunter.jobs import Job
from job_hunter.matching import score_job
from job_hunter.search import collect, http_client, rank
from job_hunter.tailor import TailorRequest, annotate, apply, save
from job_hunter.vocabulary import cv_terms, find_terms

INSTRUCTIONS = """\
Tools for the job search of the person whose CV is in profile/cv.yaml.

Ground rules:
- The CV is the only source of truth. Never claim a skill, tool, employer, date,
  number or achievement that get_cv does not show. When a job wants something
  the CV lacks, say so plainly instead of hiding the gap.
- To tailor the CV: call get_cv (for the ids), match_job with the full job
  description, then tailor_cv. tailor_cv rejects invented claims; if it returns
  problems, fix them rather than working around them.
- Rewording is fine when it stays true to the original bullet: use the job's
  vocabulary for things the person really did.
- send_to_phone delivers a message to the user's phone (Telegram and/or WhatsApp).
"""

mcp = MCPServer("job-hunter", instructions=INSTRUCTIONS)

# Jobs from the latest search, so get_job can return the full description.
_last_jobs: dict[str, Job] = {}


def _cv() -> dict:
    return config.load_cv()


@mcp.tool()
def get_cv() -> str:
    """The master CV as YAML, with ids (e1.r1.b2 = job 1, role 1, bullet 2; p1 = project 1)
    that tailor_cv uses. Items with include: false are hidden by default but true."""
    return yaml.safe_dump(annotate(_cv()), sort_keys=False, allow_unicode=True)


@mcp.tool()
def search_jobs(
    query: str = "",
    where: Literal["south_africa", "remote", "both"] = "both",
    limit: int = 10,
) -> dict[str, Any]:
    """Search South African jobs (Jooble, Adzuna) and remote jobs open to South Africa (Remotive),
    ranked by how well they fit the CV. Leave query empty to use the saved searches
    in profile/search.yaml. Each result has a 0-100 score, matched and missing skills."""
    settings = config.SearchSettings.load()
    with http_client() as client:
        collected = collect(client, settings, query=query.strip(), where=where)
    ranked = rank(collected.jobs, cv_terms(_cv()), settings)
    _last_jobs.clear()
    _last_jobs.update({job.id: job for job in collected.jobs})
    results = []
    for job, match in ranked[: max(1, min(limit, 50))]:
        snippet = job.description[:300] + ("..." if len(job.description) > 300 else "")
        results.append(
            {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "posted": job.posted,
                "salary": job.salary,
                "url": job.url,
                "score": match.score,
                "matched_skills": match.matched,
                "missing_skills": match.missing,
                "notes": match.notes,
                "snippet": snippet,
            }
        )
    return {
        "results": results,
        "found": len(collected.jobs),
        "notes": collected.notes,
        "errors": collected.errors,
    }


@mcp.tool()
def get_job(job_id: str) -> dict[str, Any]:
    """Full details of a job from the latest search_jobs call. Adzuna only provides a
    short description; for tailoring, ask the user to paste the full advert if needed."""
    job = _last_jobs.get(job_id)
    if job is None:
        return {"error": f"{job_id} is not in the latest search results. Run search_jobs first."}
    return job.to_dict()


@mcp.tool()
def match_job(job_description: str, job_title: str = "") -> dict[str, Any]:
    """How well the CV fits a job description (pasted text): score, skills the CV has
    and lacks, and the CV bullets and projects most relevant to this job, best first."""
    cv = annotate(_cv())
    settings = config.SearchSettings.load()
    match = score_job(job_title, job_description, cv_terms(cv), settings)
    wanted = find_terms(f"{job_title}\n{job_description}")

    def relevance(text: str, tags: list[str]) -> list[str]:
        return sorted(find_terms(text + " " + " ".join(t.replace("-", " ") for t in tags)) & wanted)

    bullets = []
    for job in cv.get("experience", []):
        for role in job.get("roles", []):
            for bullet in role.get("bullets", []):
                hits = relevance(bullet["text"], bullet.get("tags", []))
                if hits:
                    bullets.append(
                        {"id": bullet["id"], "role": role["title"], "text": bullet["text"], "matches": hits}
                    )
    bullets.sort(key=lambda b: len(b["matches"]), reverse=True)
    projects = [
        {"id": p["id"], "name": p["name"], "matches": hits}
        for p in cv.get("projects", [])
        if (hits := relevance(" ".join(p.get("bullets", [])), p.get("tags", [])))
    ]
    projects.sort(key=lambda p: len(p["matches"]), reverse=True)
    return {**match.to_dict(), "relevant_bullets": bullets[:15], "relevant_projects": projects}


@mcp.tool()
def tailor_cv(
    job_title: str,
    company: str,
    summary: str | None = None,
    headline: str | None = None,
    skills: list[dict[str, Any]] | None = None,
    bullet_order: list[str] | None = None,
    hide_bullets: list[str] | None = None,
    rewrites: dict[str, str] | None = None,
    projects: list[str] | None = None,
    show_experience: list[str] | None = None,
    hide_experience: list[str] | None = None,
) -> dict[str, Any]:
    """Create a CV tailored to one job and save it as a Word file.

    - summary / headline: new text, using only technologies and numbers in the CV.
    - skills: [{"group": ..., "items": [...]}] to reorder or regroup; only existing skills.
    - bullet_order: bullet ids to move to the top of their role, most relevant first.
    - hide_bullets: bullet ids to leave out. rewrites: {bullet id: reworded text}.
    - projects: project ids to show, in order. show_experience / hide_experience: job ids.

    Returns the file path, or the problems that stopped it (nothing is saved then)."""
    req = TailorRequest(
        job_title=job_title,
        company=company,
        summary=summary,
        headline=headline,
        skills=skills,
        bullet_order=bullet_order or [],
        hide_bullets=hide_bullets or [],
        rewrites=rewrites or {},
        projects=projects,
        show_experience=show_experience or [],
        hide_experience=hide_experience or [],
    )
    master = _cv()
    result = apply(master, req)
    if not result.ok:
        return {"ok": False, "problems": result.problems}
    save(result, req, config.output_dir(), master["basics"]["name"])
    return {"ok": True, "docx": result.docx_path, "record": result.yaml_path, "changes": result.changes}


@mcp.tool()
def send_to_phone(message: str) -> str:
    """Send a message to the user's phone, e.g. a shortlist of jobs, through every
    configured channel: Telegram, and WhatsApp if set up (WhatsApp delivers free text
    only within 24 hours of the user's last message to the business number)."""
    if not notify.configured():
        return f"Not sent: no phone channel is set up. {notify.SETUP_HINT}"
    with http_client() as client:
        delivery = notify.send_text(client, message)
    parts = []
    if delivery.sent:
        parts.append("Sent via " + " and ".join(delivery.sent) + ".")
    parts += [f"Not sent via {e}" for e in delivery.errors]
    return " ".join(parts)


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
