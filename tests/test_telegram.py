import httpx
import pytest

from job_hunter.telegram import TelegramConfig, TelegramError, send_text

from .conftest import body, fake_api

CFG = TelegramConfig(token="123:abc", chat_id="555")


def test_config_from_env(monkeypatch):
    assert TelegramConfig.from_env() is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")
    assert TelegramConfig.from_env() == CFG


def test_send_text_plain_and_html():
    calls: list[httpx.Request] = []
    with fake_api(calls=calls)() as client:
        assert send_text(client, CFG, "hello") == 42
        send_text(client, CFG, "<b>hi</b>", html=True)
    assert "parse_mode" not in body(calls[0])
    assert body(calls[1])["parse_mode"] == "HTML"
    assert body(calls[0])["link_preview_options"] == {"is_disabled": True}


@pytest.mark.parametrize(
    ("status", "description", "hint"),
    [
        (401, "Unauthorized", "bot token is wrong"),
        (403, "Forbidden: bot was blocked by the user", "press Start"),
        (400, "Bad Request: chat not found", "TELEGRAM_CHAT_ID is wrong"),
    ],
)
def test_errors_are_explained_without_the_token(status, description, hint):
    def reply(_request):
        return httpx.Response(status, json={"ok": False, "error_code": status, "description": description})

    with fake_api(telegram=reply)() as client, pytest.raises(TelegramError) as caught:
        send_text(client, CFG, "x")
    assert hint in str(caught.value)
    assert "123:abc" not in str(caught.value)


def test_network_errors_do_not_leak_the_url():
    def boom(request):
        raise httpx.ConnectError("connection failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(TelegramError) as caught:
        send_text(client, CFG, "x")
    assert "123:abc" not in str(caught.value) and "ConnectError" in str(caught.value)
