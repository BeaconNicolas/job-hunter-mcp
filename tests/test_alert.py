import httpx

from job_hunter import alert

from .conftest import BAD, GOOD, adzuna_item, body, fake_api, remotive_item


def use_api(monkeypatch, **kwargs):
    monkeypatch.setattr(alert, "http_client", fake_api(**kwargs))


def whatsapp_env(monkeypatch, template=True):
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("WHATSAPP_TO", "27680000000")
    if template:
        monkeypatch.setenv("WHATSAPP_TEMPLATE", "job_alert")


def test_sends_new_matches_once(monkeypatch, isolated):
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    whatsapp_env(monkeypatch)
    summary = isolated / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    calls: list[httpx.Request] = []
    use_api(
        monkeypatch,
        adzuna=[adzuna_item("1", "Platform Engineer", GOOD), adzuna_item("2", "Java Developer", BAD, "Bank")],
        remotive=[remotive_item(7, "DevOps Engineer", GOOD)],
        calls=calls,
    )

    assert alert.run() == 0
    sent = [body(r) for r in calls if r.url.host == "graph.facebook.com"]
    assert len(sent) == 1
    count, listing = (p["text"] for p in sent[0]["template"]["components"][0]["parameters"])
    assert count == "2"
    assert "Platform Engineer" in listing and "DevOps Engineer" in listing and "Java" not in listing
    assert "(sent)" in summary.read_text()

    # Second run: same jobs, nothing new to send.
    calls.clear()
    assert alert.run() == 0
    assert not [r for r in calls if r.url.host == "graph.facebook.com"]


def test_without_adzuna_keys_still_searches_remote(monkeypatch, capsys):
    calls: list[httpx.Request] = []
    use_api(monkeypatch, remotive=[remotive_item(7, "DevOps Engineer", GOOD)], calls=calls)
    assert alert.run() == 0
    out = capsys.readouterr().out
    assert "Adzuna skipped" in out
    assert "WhatsApp not configured" not in out  # printed in the summary, not as an error
    assert "DevOps Engineer" in out
    assert {r.url.host for r in calls} == {"remotive.com"}


def test_dry_run_sends_and_remembers_nothing(monkeypatch):
    whatsapp_env(monkeypatch)
    calls: list[httpx.Request] = []
    use_api(monkeypatch, remotive=[remotive_item(7, "DevOps Engineer", GOOD)], calls=calls)
    assert alert.run(dry_run=True) == 0
    assert alert.run(dry_run=True) == 0
    assert not [r for r in calls if r.url.host == "graph.facebook.com"]


def test_failed_send_is_retried_next_time(monkeypatch):
    whatsapp_env(monkeypatch, template=False)
    use_api(
        monkeypatch,
        remotive=[remotive_item(7, "DevOps Engineer", GOOD)],
        whatsapp=lambda _r: httpx.Response(400, json={"error": {"code": 131047, "message": "Re-engagement"}}),
    )
    assert alert.run() == 1
    calls: list[httpx.Request] = []
    use_api(monkeypatch, remotive=[remotive_item(7, "DevOps Engineer", GOOD)], calls=calls)
    assert alert.run() == 0
    text = body([r for r in calls if r.url.host == "graph.facebook.com"][0])["text"]["body"]
    assert "DevOps Engineer" in text


def test_long_listing_fits_in_a_template_variable():
    from job_hunter.jobs import Job
    from job_hunter.matching import Match

    jobs = [
        (
            Job(
                f"a:{i}",
                "a",
                "Cloud Engineer " * 3,
                "Company",
                "Johannesburg",
                "https://x.example/" + "y" * 200,
                "",
            ),
            Match(80),
        )
        for i in range(5)
    ]
    listing = alert.template_listing(jobs)
    assert len(listing) <= 1000 and "more in the GitHub Actions summary" in listing


def test_public_actions_logs_hide_job_details(monkeypatch, isolated, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    summary = isolated / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    use_api(monkeypatch, remotive=[remotive_item(7, "DevOps Engineer", GOOD)])
    assert alert.run(dry_run=True) == 0
    out = capsys.readouterr().out
    assert "DevOps Engineer" not in out and "DevOps Engineer" not in summary.read_text()
    assert "ALERT_DETAILS_IN_LOGS" in summary.read_text()

    monkeypatch.setenv("ALERT_DETAILS_IN_LOGS", "true")
    assert alert.run(dry_run=True) == 0
    assert "DevOps Engineer" in capsys.readouterr().out
