from docx import Document

from job_hunter.render import render_docx


def test_profile_files_load(cv, settings):
    assert cv["basics"]["name"]
    assert settings.adzuna_country == "za"
    assert settings.min_score > 0


def test_master_cv_renders_with_contact_details(cv, tmp_path):
    path = render_docx(cv, tmp_path / "cv.docx")
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert cv["basics"]["email"] in text and cv["basics"]["phone"] in text
    # Hidden by default (include: false).
    assert "Inkululeko" not in text
