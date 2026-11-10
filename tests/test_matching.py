from job_hunter.matching import excluded, required_years, score_job
from job_hunter.vocabulary import cv_terms

from .conftest import BAD, GOOD


def test_good_fit_scores_high(cv, settings):
    match = score_job("Platform Engineer", GOOD, cv_terms(cv), settings)
    assert match.score >= 80
    assert match.title_fit == "target"
    assert match.missing == []


def test_poor_fit_scores_low(cv, settings):
    match = score_job("Java Developer", BAD, cv_terms(cv), settings)
    assert match.score < settings.min_score
    assert "Java" in match.missing


def test_flags_experience_gap(cv, settings):
    match = score_job("DevOps Engineer", GOOD + " You have 7+ years of experience.", cv_terms(cv), settings)
    assert match.required_years == 7
    assert any("7+ years" in note for note in match.notes)
    assert match.score < score_job("DevOps Engineer", GOOD, cv_terms(cv), settings).score


def test_required_years_needs_experience_nearby():
    assert required_years("Minimum 3-5 years experience in DevOps") == 3
    assert required_years("We were founded 25 years ago.") is None


def test_excluded_titles(settings):
    assert excluded("Principal Cloud Architect", settings)
    assert not excluded("Cloud Engineer", settings)


def test_unrelated_title_never_reaches_the_alert_threshold(cv, settings):
    """A Remote Office Assistant advert that only mentions Excel used to score 55."""
    match = score_job("Remote Office Assistant", "Strong Excel skills and attention to detail.", cv_terms(cv), settings)
    assert match.title_fit == "none"
    assert match.score < settings.min_score
    assert any("not a cloud" in note for note in match.notes)


def test_one_matching_skill_is_not_full_coverage(cv, settings):
    one = score_job("Cloud Engineer", "You know Python.", cv_terms(cv), settings)
    many = score_job("Cloud Engineer", GOOD, cv_terms(cv), settings)
    assert one.score < many.score
