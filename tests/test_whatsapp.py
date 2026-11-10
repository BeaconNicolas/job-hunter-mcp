import httpx
import pytest

from job_hunter.whatsapp import WhatsAppConfig, WhatsAppError, send, template_param, template_payload

from .conftest import body, fake_api

CFG = WhatsAppConfig(token="t", phone_number_id="123", to="27680000000", template="job_alert")


def test_config_from_env(monkeypatch):
    assert WhatsAppConfig.from_env() is None
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setenv("WHATSAPP_TO", "+27 68 000 0000")
    cfg = WhatsAppConfig.from_env()
    assert cfg.to == "27680000000" and cfg.template is None


def test_template_params_have_no_newlines():
    assert template_param("a\nb\t c      d") == "a | b | c   d"
    assert len(template_param("x" * 2000)) == 1000


def test_send_template():
    calls: list[httpx.Request] = []
    with fake_api(calls=calls)() as client:
        message_id = send(client, CFG, template_payload(CFG, ["2", "line one\nline two"]))
    assert message_id == "wamid.TEST"
    sent = body(calls[0])
    assert calls[0].url.path == "/v25.0/123/messages"
    assert calls[0].headers["Authorization"] == "Bearer t"
    assert sent["template"]["name"] == "job_alert"
    assert sent["template"]["components"][0]["parameters"][1]["text"] == "line one | line two"


def test_error_explains_24_hour_window():
    def reply(_request):
        return httpx.Response(400, json={"error": {"code": 131047, "message": "Re-engagement message"}})

    with fake_api(whatsapp=reply)() as client, pytest.raises(WhatsAppError, match="24 hours"):
        send(client, CFG, {"to": "x"})
