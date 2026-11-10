"""Daily job alert: search, rank against the CV, and send the best new matches to your phone.

    job-hunter-alert             # search and send
    job-hunter-alert --dry-run   # search and print, send nothing, remember nothing

Run every morning by .github/workflows/daily-alert.yml. Jobs already sent are
remembered in state/seen_jobs.json (kept between runs by the Actions cache).
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

from job_hunter import config, notify
from job_hunter.jobs import Job
from job_hunter.matching import Match
from job_hunter.search import collect, http_client, rank
from job_hunter.vocabulary import cv_terms

KEEP_SEEN_DAYS = 45


# ----------------------------------------------------------------- seen jobs
def load_seen(path: Path) -> dict[str, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("jobs", {})
    except (FileNotFoundError, ValueError):
        return {}


def save_seen(path: Path, seen: dict[str, str], today: date) -> None:
    cutoff = (today - timedelta(days=KEEP_SEEN_DAYS)).isoformat()
    kept = {job_id: day for job_id, day in seen.items() if day >= cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"jobs": kept}, indent=1, sort_keys=True), encoding="utf-8")


# ----------------------------------------------------------------- logs
def details_in_logs() -> bool:
    """Show job titles in logs? Always locally. On GitHub Actions only when the
    ALERT_DETAILS_IN_LOGS variable is "true": logs of a public repository are public."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return True
    return (os.environ.get("ALERT_DETAILS_IN_LOGS") or "").strip().lower() == "true"


HIDDEN_NOTE = (
    "Job details are hidden here because anyone can read this repository's Actions logs. "
    "They go to your phone only. To show them, set the repository variable ALERT_DETAILS_IN_LOGS to true."
)


def write_summary(good: list[tuple[Job, Match]], sent: list[tuple[Job, Match]], notes: list[str]) -> None:
    """Counts, notes and (when allowed) a table of matches in the GitHub Actions run summary."""
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return
    if not details_in_logs():
        body = [f"## Job matches ({len(good)} at or above the minimum score, {len(sent)} sent)", ""]
        body += [f"> {note}" for note in notes + [HIDDEN_NOTE]]
        with open(target, "a", encoding="utf-8") as handle:
            handle.write("\n".join(body) + "\n")
        return
    sent_ids = {job.id for job, _ in sent}
    rows = [
        "| Score | Job | Company | Location | Posted | Missing from your CV |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for job, match in good[:30]:
        mark = " (sent)" if job.id in sent_ids else ""
        title = job.title.replace("|", "/")
        missing = ", ".join(match.missing[:6]) or "-"
        cells = [
            str(match.score),
            f"[{title}]({job.url}){mark}",
            job.company,
            job.location,
            job.posted,
            missing,
        ]
        rows.append("| " + " | ".join(cells) + " |")
    body = [f"## Job matches ({len(good)} at or above the minimum score, {len(sent)} sent)", ""]
    body += [f"> {note}" for note in notes] + ([""] if notes else [])
    body += rows if good else ["No matches today."]
    with open(target, "a", encoding="utf-8") as handle:
        handle.write("\n".join(body) + "\n")


# ----------------------------------------------------------------- main
PREVIEW_SIZE = 10


def run(dry_run: bool = False, preview: bool = False, today: date | None = None) -> int:
    """preview: send the 10 best-scoring jobs, whatever their score, without marking
    them as sent. For checking how the scoring treats real adverts."""
    today = today or date.today()
    settings = config.SearchSettings.load()
    have = cv_terms(config.load_cv())
    state = config.state_file()

    with http_client() as client:
        collected = collect(client, settings, log=print)
        for note in collected.notes:
            print(f"Note: {note}")
        for error in collected.errors:
            print(f"Warning: {error}")
        if not collected.jobs and collected.errors:
            print("Every source failed; nothing to rank.")
            return 1

        ranked = rank(collected.jobs, have, settings)
        good = [pair for pair in ranked if pair[1].score >= settings.min_score]
        seen = load_seen(state)
        new = [pair for pair in good if pair[0].id not in seen]
        top = new[: settings.max_alerts]
        print(f"{len(collected.jobs)} jobs found, {len(good)} scored {settings.min_score}+, {len(new)} new.")

        channels = notify.configured()
        notes = list(collected.notes)
        if not channels:
            notes.append(f"No phone channel configured. {notify.SETUP_HINT}")

        if preview:
            sample = ranked[:PREVIEW_SIZE]
            heading = (
                f"Preview: the {len(sample)} best-scoring jobs today (alerts start at {settings.min_score})"
            )
            if not sample or not channels:
                reason = "Nothing to preview." if not sample else "No phone channel configured."
                print(f"{reason} {notify.SETUP_HINT}" if sample else reason)
                return 0
            delivery = notify.send_jobs(client, sample, heading=heading)
            for error in delivery.errors:
                print(f"Sending failed: {error}")
            print(f"Preview of {len(sample)} job(s) sent; nothing marked as sent." if delivery.sent else "")
            return 0 if delivery.sent else 1

        if not top:
            print("No new matches to send today.")
            write_summary(good, [], notes)
            return 0

        if dry_run or not channels:
            if details_in_logs():
                print("\n" + notify.plain_message(top))
            else:
                print(f"{len(top)} job(s) would be sent. {HIDDEN_NOTE}")
            write_summary(good, [], notes + (["Dry run: nothing was sent."] if dry_run else []))
            return 0

        delivery = notify.send_jobs(client, top)

    for error in delivery.errors:
        print(f"Sending failed: {error}")
    if not delivery.sent:
        write_summary(good, [], notes + [f"Sending failed: {e}" for e in delivery.errors])
        return 1

    print(f"Sent {len(top)} job(s) to {' and '.join(delivery.sent)}.")
    for job, _ in top:
        seen[job.id] = today.isoformat()
    save_seen(state, seen, today)
    write_summary(good, top, notes + [f"Sending failed: {e}" for e in delivery.errors])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the matches; send and remember nothing")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="send the 10 best-scoring jobs, whatever their score; remember nothing",
    )
    args = parser.parse_args(argv)
    return run(dry_run=args.dry_run, preview=args.preview)


if __name__ == "__main__":
    raise SystemExit(main())
