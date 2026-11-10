import asyncio

import yaml
from mcp import Client

from job_hunter import search, server

from .conftest import GOOD, fake_api, remotive_item


def call(tool: str, args: dict | None = None):
    async def go():
        async with Client(server.mcp) as client:
            return await client.call_tool(tool, args or {})

    return asyncio.run(go())


def test_lists_all_tools():
    async def go():
        async with Client(server.mcp) as client:
            return {t.name for t in (await client.list_tools()).tools}

    assert asyncio.run(go()) == {
        "get_cv",
        "search_jobs",
        "get_job",
        "match_job",
        "tailor_cv",
        "send_to_phone",
    }


def test_get_cv_has_ids():
    result = call("get_cv")
    cv = yaml.safe_load(result.content[0].text)
    assert cv["experience"][0]["roles"][0]["bullets"][0]["id"] == "e1.r1.b1"


def test_search_then_get_job(monkeypatch):
    monkeypatch.setattr(search, "http_client", fake_api(remotive=[remotive_item(7, "DevOps Engineer", GOOD)]))
    monkeypatch.setattr(server, "http_client", search.http_client)
    found = call("search_jobs", {"where": "remote"}).structured_content
    assert found["results"][0]["id"] == "remotive:7"
    job = call("get_job", {"job_id": "remotive:7"}).structured_content
    assert job["description"] == GOOD


def test_tailor_cv_refuses_then_succeeds(isolated):
    bad = call(
        "tailor_cv", {"job_title": "SRE", "company": "Acme", "summary": "Kubernetes expert."}
    ).structured_content
    assert bad["ok"] is False and "Kubernetes" in bad["problems"][0]
    good = call(
        "tailor_cv",
        {"job_title": "SRE", "company": "Acme", "bullet_order": ["e1.r2.b1"], "projects": ["p1"]},
    ).structured_content
    assert good["ok"] is True
    assert good["docx"].startswith(str(isolated / "output"))


def test_send_to_phone(monkeypatch):
    text = call("send_to_phone", {"message": "hi"}).content[0].text
    assert "no phone channel" in text and "TELEGRAM_BOT_TOKEN" in text

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(server, "http_client", fake_api())
    assert call("send_to_phone", {"message": "hi"}).content[0].text == "Sent via Telegram."
