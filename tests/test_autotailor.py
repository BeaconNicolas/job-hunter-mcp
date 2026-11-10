"""Automatic tailoring, with a stand-in for the Claude API (no network, no key)."""

import json
from datetime import date
from types import SimpleNamespace

import httpx
import yaml

from job_hunter import alert, autotailor, config
from job_hunter.jobs import Job

from .conftest import GOOD, body, fake_api, remotive_item

TODAY = date(2026, 11, 10)

JOB = Job(
    id="remotive:7",
    source="remotive",
    title="DevOps Engineer",
    company="Remote Co",
    location="Worldwide",
    url="https://remotive.com/remote-jobs/devops/7",
    description=GOOD,
)


def plan(**overrides):
    base = {
        "headline": "Platform Engineer | AWS, Terraform, CI/CD, Docker",
        "summary": "Platform engineer who builds AWS platforms with Terraform and CI/CD pipelines.",
        "skills": [{"group": "Most relevant", "items": ["Terraform", "CI/CD pipelines", "Docker", "Python"]}],
        "bullet_order": ["e1.r2.b5", "e1.r2.b1"],
        "hide_bullets": [],
        "rewrites": [{"id": "e1.r2.b1", "text": "Restored deployments by fixing broken AWS CI/CD pipelines."}],
        "projects": ["p1"],
        "show_experience": [],
        "fit_note": "Strong match on AWS, Terraform and CI/CD.",
    }
    base.update(overrides)
    return json.dumps(base)


class FakeClaude:
    """Answers beta.messages.create with the given JSON replies, in order."""

    def __init__(self, *replies, stop_reason="end_turn"):
        self.replies = list(replies)
        self.stop_reason = stop_reason
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        text = self.replies.pop(0)
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=text)])


def run(client, cv, tmp_path, model="claude-opus-5-5"):
    return autotailor.tailor_job(client, cv, JOB, model=model, effort="medium", output_dir=tmp_path, today=TODAY)


def test_good_plan_becomes_a_word_file(cv, tmp_path):
    client = FakeClaude(plan())
    result = run(client, cv, tmp_path)
    assert result.ok and result.attempts == 1
    assert result.docx_path.endswith("_CV.docx")
    assert "Strong match" in result.fit_note

    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and call["betas"] == [autotailor.FALLBACK_BETA]
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "<cv>" in call["system"][0]["text"] and "e1.r1.b1" in call["system"][0]["text"]
    assert "DevOps Engineer" in call["messages"][0]["content"]


def test_invented_skill_is_sent_back_for_correction(cv, tmp_path):
    bad = plan(skills=[{"group": "Cloud", "items": ["AWS", "Kubernetes"]}])
    client = FakeClaude(bad, plan())
    result = run(client, cv, tmp_path)
    assert result.ok and result.attempts == 2
    correction = client.calls[1]["messages"][-1]["content"]
    assert "Kubernetes" in correction and "corrected plan" in correction


def test_gives_up_after_three_bad_plans(cv, tmp_path):
    bad = plan(summary="Kubernetes expert with 9 years of Azure.")
    result = run(FakeClaude(bad, bad, bad), cv, tmp_path)
    assert not result.ok and "3 tries" in result.error
    assert not list(tmp_path.rglob("*.docx"))


def test_refusal_is_reported(cv, tmp_path):
    result = run(FakeClaude(plan(), stop_reason="refusal"), cv, tmp_path)
    assert not result.ok and "declined" in result.error


def test_no_fallback_parameters_for_models_without_them(cv, tmp_path):
    client = FakeClaude(plan())
    run(client, cv, tmp_path, model="claude-haiku-5-5")
    assert "fallbacks" not in client.calls[0] and "betas" not in client.calls[0]


def test_snippet_adverts_are_flagged_in_the_prompt():
    job = Job(**{**JOB.__dict__, "extra": {"description_is_snippet": True}})
    assert "short excerpt" in autotailor.job_prompt(job)


def test_caption_fits_telegram():
    result = autotailor.AutoTailorResult(JOB, ok=True, changes=["x" * 2000], fit_note="Good fit.")
    assert len(autotailor.caption(result, 80)) <= 1024


# ----------------------------------------------------------------- inside the daily alert
def enable_tailoring(monkeypatch, tmp_path, fake):
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "cv.yaml").write_text(yaml.safe_dump(config.load_cv()), encoding="utf-8")
    settings = yaml.safe_load((config.profile_dir() / "search.yaml").read_text(encoding="utf-8"))
    settings["tailoring"] = {"enabled": True, "max_per_day": 1, "model": "claude-opus-5-5", "effort": "medium"}
    (profile / "search.yaml").write_text(yaml.safe_dump(settings), encoding="utf-8")
    monkeypatch.setattr(config, "profile_dir", lambda: profile)
    monkeypatch.setattr(alert, "claude_client", lambda: fake)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")


def test_alert_sends_a_tailored_cv_to_telegram(monkeypatch, tmp_path, capsys):
    enable_tailoring(monkeypatch, tmp_path, FakeClaude(plan()))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    calls: list[httpx.Request] = []
    jobs = [remotive_item(7, "DevOps Engineer", GOOD), remotive_item(8, "Cloud Engineer", GOOD)]
    monkeypatch.setattr(alert, "http_client", fake_api(remotive=jobs, calls=calls))
    assert alert.run(today=TODAY) == 0

    docs = [r for r in calls if r.url.path.endswith("/sendDocument")]
    assert len(docs) == 1  # max_per_day: 1
    assert b'filename="2026-11-10_' in docs[0].content and b"Tailored CV:" in docs[0].content
    assert "Tailored and sent 1 of 1" in capsys.readouterr().out
    assert any(r.url.path.endswith("/sendMessage") and "DevOps" in body(r)["text"] for r in calls)


def test_alert_without_anthropic_key_skips_tailoring(monkeypatch, tmp_path, capsys):
    fake = FakeClaude()
    enable_tailoring(monkeypatch, tmp_path, fake)
    monkeypatch.setattr(alert, "http_client", fake_api(remotive=[remotive_item(7, "DevOps Engineer", GOOD)]))
    assert alert.run(today=TODAY) == 0
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out
    assert fake.calls == []
