from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from job_hunter import config

SECRET_VARS = [
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
    "WHATSAPP_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_TO",
    "WHATSAPP_TEMPLATE",
    "WHATSAPP_TEMPLATE_LANG",
    "WHATSAPP_API_VERSION",
]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real secrets, and outputs/state in a temporary folder."""
    for name in SECRET_VARS + ["GITHUB_STEP_SUMMARY"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JOB_HUNTER_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setenv("JOB_HUNTER_STATE", str(tmp_path / "state" / "seen.json"))
    return tmp_path


@pytest.fixture
def cv() -> dict:
    return config.load_cv()


@pytest.fixture
def settings() -> config.SearchSettings:
    return config.SearchSettings.load()


def adzuna_item(job_id: str, title: str, description: str, company: str = "Acme") -> dict:
    return {
        "id": job_id,
        "title": title,
        "description": description,
        "company": {"display_name": company},
        "location": {"display_name": "Pretoria, Gauteng"},
        "redirect_url": f"https://www.adzuna.co.za/details/{job_id}",
        "created": "2026-11-06T08:00:00Z",
        "salary_min": 600000,
        "salary_max": 800000,
    }


def remotive_item(job_id: int, title: str, description: str, location: str = "Worldwide") -> dict:
    return {
        "id": job_id,
        "title": title,
        "company_name": "Remote Co",
        "candidate_required_location": location,
        "url": f"https://remotive.com/remote-jobs/devops/{job_id}",
        "description": f"<p>{description}</p>",
        "publication_date": "2026-11-05T10:00:00",
        "salary": "",
    }


GOOD = "Build AWS infrastructure with Terraform, CI/CD pipelines in GitHub Actions, Docker and Python."
BAD = "Java and Spring Boot developer for a banking core system, Oracle database, on-premise."


def fake_api(
    adzuna: list[dict] | None = None,
    remotive: list[dict] | None = None,
    whatsapp: Callable[[httpx.Request], httpx.Response] | None = None,
    calls: list[httpx.Request] | None = None,
) -> Callable[[], httpx.Client]:
    """A factory for httpx clients that answer like the real APIs."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        host = request.url.host
        if host == "api.adzuna.com":
            return httpx.Response(200, json={"results": adzuna or []})
        if host == "remotive.com":
            return httpx.Response(200, json={"jobs": remotive or []})
        if host == "graph.facebook.com":
            if whatsapp:
                return whatsapp(request)
            return httpx.Response(200, json={"messages": [{"id": "wamid.TEST"}]})
        return httpx.Response(404)

    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def body(request: httpx.Request) -> dict:
    return json.loads(request.content)
