import pytest

from app import main

CODE = "test-code-123"


@pytest.fixture()
def gated(monkeypatch):
    monkeypatch.setattr(main, "ACCESS_CODE", CODE)


def test_no_code_configured_means_open(client, seed_analysis):
    analysis_id = seed_analysis([])
    assert client.get(f"/analysis/{analysis_id}").status_code == 200


def test_health_stays_open(client, gated):
    assert client.get("/health").status_code == 200


def test_requests_without_code_are_rejected(client, gated, seed_analysis):
    analysis_id = seed_analysis([])
    assert client.get(f"/analysis/{analysis_id}").status_code == 401
    assert client.post("/analyze", json={"repo_url": "https://github.com/o/r"}).status_code == 401


def test_wrong_code_is_rejected(client, gated, seed_analysis):
    analysis_id = seed_analysis([])
    resp = client.get(f"/analysis/{analysis_id}", headers={"X-Access-Code": "nope"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Access code required"


def test_correct_code_is_accepted(client, gated, seed_analysis):
    analysis_id = seed_analysis([])
    resp = client.get(f"/analysis/{analysis_id}", headers={"X-Access-Code": CODE})
    assert resp.status_code == 200


def test_rejected_request_does_no_work(client, gated, monkeypatch):
    def must_not_run(*args, **kwargs):
        raise AssertionError("nothing may run without the access code")

    monkeypatch.setattr(main, "run_analysis", must_not_run)
    monkeypatch.setattr(main, "validate_repo_url", must_not_run)

    resp = client.post("/analyze", json={"repo_url": "https://github.com/o/r"})

    assert resp.status_code == 401


def test_browser_preflight_works_without_the_code(client, gated):
    resp = client.options(
        "/analyze",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-access-code",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"