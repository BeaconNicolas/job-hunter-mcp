import httpx

from job_hunter import alert, notify

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
    listing = notify.template_listing(jobs)
    assert len(listing) <= 1000 and "more: ask Claude" in listing


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


def test_adzuna_failure_is_reported_without_the_key(monkeypatch, capsys):
    """When Adzuna's test calls run out, the alert carries on with Remotive and never
    prints the request URL (it contains the API key)."""
    monkeypatch.setenv("ADZUNA_APP_ID", "my-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "super-secret-key")
    real = fake_api(remotive=[remotive_item(7, "DevOps Engineer", GOOD)])

    def factory():
        client = real()
        original = client._transport.handle_request

        def handle(request):
            if request.url.host == "api.adzuna.com":
                return httpx.Response(403, request=request)
            return original(request)

        client._transport.handle_request = handle
        return client

    monkeypatch.setattr(alert, "http_client", factory)
    assert alert.run(dry_run=True) == 0
    out = capsys.readouterr().out
    assert "HTTP 403" in out and "call limit" in out
    assert "super-secret-key" not in out
    assert "DevOps Engineer" in out


def telegram_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654")


def test_sends_to_telegram(monkeypatch):
    telegram_env(monkeypatch)
    calls: list[httpx.Request] = []
    use_api(monkeypatch, remotive=[remotive_item(7, "DevOps Engineer & SRE", GOOD)], calls=calls)
    assert alert.run() == 0
    sent = [r for r in calls if r.url.host == "api.telegram.org"]
    assert len(sent) == 1
    assert sent[0].url.path == "/bot123:secret-token/sendMessage"
    payload = body(sent[0])
    assert payload["chat_id"] == "987654" and payload["parse_mode"] == "HTML"
    assert "<b>DevOps Engineer &amp; SRE</b>" in payload["text"]
    assert 'href="https://remotive.com/remote-jobs/devops/7"' in payload["text"]


def test_one_channel_failing_still_counts_as_sent(monkeypatch, capsys):
    telegram_env(monkeypatch)
    whatsapp_env(monkeypatch)
    locked = {"error": {"code": 131031, "message": "Business Account locked"}}
    use_api(
        monkeypatch,
        remotive=[remotive_item(7, "DevOps Engineer", GOOD)],
        whatsapp=lambda _r: httpx.Response(400, json=locked),
    )
    assert alert.run() == 0
    out = capsys.readouterr().out
    assert "Sent 1 job(s) to Telegram." in out
    assert "131031" in out


def test_telegram_errors_never_show_the_token(monkeypatch, capsys):
    telegram_env(monkeypatch)
    not_found = {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
    use_api(
        monkeypatch,
        remotive=[remotive_item(7, "DevOps Engineer", GOOD)],
        telegram=lambda _r: httpx.Response(400, json=not_found),
    )
    assert alert.run() == 1
    out = capsys.readouterr().out
    assert "pressed Start" in out
    assert "secret-token" not in out
