from job_hunter.vocabulary import cv_terms, find_terms


def test_finds_aliases():
    assert find_terms("Experience with k8s and continuous integration") == {"Kubernetes", "CI/CD"}
    assert "CI/CD" in find_terms("CI / CD pipelines")


def test_does_not_confuse_similar_words():
    assert find_terms("JavaScript only") == {"JavaScript"}
    assert "SQL" not in find_terms("MySQL and NoSQL")
    assert "Git" not in find_terms("GitHub")


def test_cv_terms_come_from_the_cv(cv):
    have = cv_terms(cv)
    assert {"AWS", "Terraform", "Python", "Docker", "CI/CD", "GitHub Actions"} <= have
    # Not in the CV, so never treated as a skill the person has.
    assert not {"Kubernetes", "Azure", "Java", "Ansible"} & have
