from datetime import date

from docx import Document

from job_hunter.tailor import TailorRequest, annotate, apply, save, years_of_experience

TODAY = date(2026, 11, 7)


def req(**kwargs) -> TailorRequest:
    return TailorRequest(job_title="Platform Engineer", company="Acme Bank", **kwargs)


def test_ids_are_stable(cv):
    a = annotate(cv)
    first = a["experience"][0]["roles"][0]["bullets"][0]
    assert first["id"] == "e1.r1.b1"
    assert a["projects"][0]["id"] == "p1"


def test_rejects_skill_not_in_cv(cv):
    result = apply(cv, req(skills=[{"group": "Cloud", "items": ["AWS", "Kubernetes"]}]), TODAY)
    assert not result.ok
    assert any("Kubernetes" in p for p in result.problems)


def test_rejects_invented_technology_and_numbers_in_summary(cv):
    result = apply(
        cv, req(summary="Platform engineer with 8 years of Kubernetes and Azure experience."), TODAY
    )
    assert not result.ok
    text = " ".join(result.problems)
    assert "Azure" in text and "Kubernetes" in text and "8" in text


def test_rewrite_may_not_add_numbers(cv):
    result = apply(
        cv, req(rewrites={"e1.r2.b1": "Fixed 12 broken AWS CI/CD pipelines, restoring deployments."}), TODAY
    )
    assert not result.ok
    assert "12" in result.problems[0]


def test_rejects_unknown_ids(cv):
    result = apply(cv, req(bullet_order=["e9.r9.b9"]), TODAY)
    assert not result.ok and "unknown id" in result.problems[0]


def test_years_claim_matches_cv(cv):
    assert years_of_experience(cv, TODAY) == 3
    assert apply(cv, req(summary="Platform engineer with 3 years of AWS and Terraform experience."), TODAY).ok


def test_valid_tailoring_applies_and_renders(cv, tmp_path):
    request = req(
        headline="Platform Engineer | AWS, Terraform, CI/CD, Docker",
        summary="Platform engineer who builds AWS platforms with Terraform and CI/CD pipelines.",
        skills=[{"group": "Most relevant", "items": ["Terraform", "CI/CD pipelines", "Docker", "Python"]}],
        bullet_order=["e1.r2.b5", "e1.r2.b2"],
        hide_bullets=["e1.r4.b3"],
        rewrites={"e1.r2.b1": "Restored deployments by fixing broken AWS CI/CD pipelines."},
        projects=["p1"],
    )
    result = apply(cv, request, TODAY)
    assert result.ok, result.problems
    role = result.cv["experience"][0]["roles"][1]
    assert [b["id"] for b in role["bullets"]][:2] == ["e1.r2.b5", "e1.r2.b2"]
    assert all(b["id"] != "e1.r4.b3" for b in result.cv["experience"][0]["roles"][3]["bullets"])

    save(result, request, tmp_path, cv["basics"]["name"], TODAY)
    text = "\n".join(p.text for p in Document(result.docx_path).paragraphs)
    assert "Restored deployments by fixing broken AWS CI/CD pipelines." in text
    assert "Lending Club" not in text  # only p1 was chosen
    assert result.docx_path.endswith("2026-11-07_acme-bank_platform-engineer_beacon-nicolas-mkhabele_CV.docx")


def test_master_cv_is_not_modified(cv):
    before = repr(cv)
    apply(cv, req(summary="Platform engineer building AWS platforms with Terraform."), TODAY)
    assert repr(cv) == before
