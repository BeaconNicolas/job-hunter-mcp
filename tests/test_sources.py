import httpx

from job_hunter.jobs import dedupe, html_to_text
from job_hunter.sources import adzuna, remotive

from .conftest import GOOD, adzuna_item, body, fake_api, remotive_item


def test_adzuna_parses_results_and_sends_keys():
    calls: list[httpx.Request] = []
    with fake_api(
        adzuna=[adzuna_item("1", "<strong>Cloud</strong> Engineer", GOOD)], calls=calls
    )() as client:
        jobs = adzuna.search(client, app_id="id", app_key="key", query="cloud engineer")
    job = jobs[0]
    assert (job.id, job.title, job.company, job.posted) == (
        "adzuna:1",
        "Cloud Engineer",
        "Acme",
        "2026-11-06",
    )
    assert job.salary == "R600,000 - R800,000"
    assert calls[0].url.path == "/v1/api/jobs/za/search/1"
    assert calls[0].url.params["app_key"] == "key"


def test_remotive_keeps_only_locations_open_to_south_africa():
    items = [
        remotive_item(1, "DevOps Engineer", GOOD, "Worldwide"),
        remotive_item(2, "DevOps Engineer II", GOOD, "USA Only"),
        remotive_item(3, "SRE", GOOD, "EMEA"),
    ]
    with fake_api(remotive=items)() as client:
        jobs = remotive.search(client, category="devops", allowed_locations=["worldwide", "emea", "africa"])
    assert [j.id for j in jobs] == ["remotive:1", "remotive:3"]
    assert jobs[0].description == GOOD


def test_html_to_text_and_dedupe():
    assert html_to_text("<p>One &amp; two</p><ul><li>three</li></ul>") == "One & two\nthree"
    a = adzuna._to_job(adzuna_item("1", "Cloud Engineer", GOOD), "za")
    b = adzuna._to_job(adzuna_item("2", "Cloud Engineer", GOOD), "za")  # same title and company
    assert dedupe([a, a, b]) == [a]


def test_adzuna_any_of_is_one_call_with_what_or():
    calls: list[httpx.Request] = []
    with fake_api(calls=calls)() as client:
        adzuna.search(client, app_id="id", app_key="key", any_of=["devops", "terraform"])
    assert len(calls) == 1
    assert calls[0].url.params["what_or"] == "devops terraform"
    assert "what" not in calls[0].url.params


def jooble_item(job_id: int, title: str, snippet: str) -> dict:
    return {
        "id": job_id,
        "title": title,
        "location": "Johannesburg, Gauteng",
        "snippet": f"&nbsp;{snippet}",
        "salary": "R60 000 per month",
        "source": "careers.example.co.za",
        "type": "Full-time",
        "link": f"https://jooble.org/desc/{job_id}",
        "company": "Example Bank",
        "updated": "2026-11-09T10:00:00.0000000",
    }


def test_jooble_parses_results_and_posts_the_search():
    from job_hunter.sources import jooble

    calls: list[httpx.Request] = []
    with fake_api(jooble=[jooble_item(5, "DevOps Engineer", GOOD)], calls=calls)() as client:
        jobs = jooble.search(client, api_key="k3y", keywords="devops engineer")
    job = jobs[0]
    assert (job.id, job.company, job.posted) == ("jooble:5", "Example Bank", "2026-11-09")
    assert job.location == "Johannesburg, Gauteng"
    assert job.description == GOOD
    assert calls[0].method == "POST" and calls[0].url.path == "/api/k3y"
    assert body(calls[0])["location"] == "South Africa"
