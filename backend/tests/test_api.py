from app import main

MIXED = [
    dict(tool="ruff", category="quality", severity="low", rule_id="E402"),
    dict(tool="bandit", category="security", severity="high", rule_id="B602"),
    dict(tool="radon", category="complexity", severity="medium", rule_id="CC-D"),
    dict(tool="pip-audit", category="dependency", severity="high", rule_id="PYSEC-1"),
]


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_analyze_returns_202_and_creates_pending_analysis(client, monkeypatch):
    monkeypatch.setattr(main, "validate_repo_url", lambda url: url)
    monkeypatch.setattr(main, "run_analysis", lambda analysis_id: None)

    resp = client.post("/analyze", json={"repo_url": "https://github.com/o/r"})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"

    detail = client.get(f"/analysis/{body['id']}").json()
    assert detail["repo_url"] == "https://github.com/o/r"
    assert detail["total_findings"] == 0


def test_analyze_rejects_invalid_url_with_400(client, monkeypatch):
    def reject(url):
        raise ValueError("not a github url")

    monkeypatch.setattr(main, "validate_repo_url", reject)

    resp = client.post("/analyze", json={"repo_url": "nonsense"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "not a github url"


def test_unknown_analysis_returns_404(client):
    assert client.get("/analysis/999").status_code == 404


def test_findings_sorted_by_severity_and_counted(client, seed_analysis):
    analysis_id = seed_analysis(MIXED)

    body = client.get(f"/analysis/{analysis_id}").json()

    assert [f["rule_id"] for f in body["findings"]] == ["B602", "PYSEC-1", "CC-D", "E402"]
    assert body["total_findings"] == 4
    assert body["findings_by_severity"] == {"high": 2, "medium": 1, "low": 1}
    assert body["findings_by_tool"] == {"ruff": 1, "bandit": 1, "radon": 1, "pip-audit": 1}
    assert body["findings_by_category"] == {
        "quality": 1, "security": 1, "complexity": 1, "dependency": 1,
    }


def test_filters_narrow_the_table_but_not_the_counts(client, seed_analysis):
    analysis_id = seed_analysis(MIXED)

    by_tool = client.get(f"/analysis/{analysis_id}", params={"tool": "bandit"}).json()
    assert by_tool["total_findings"] == 1
    assert [f["rule_id"] for f in by_tool["findings"]] == ["B602"]
    assert len(by_tool["findings_by_tool"]) == 4  # summary still covers the whole analysis

    by_category = client.get(f"/analysis/{analysis_id}", params={"category": "dependency"}).json()
    assert [f["rule_id"] for f in by_category["findings"]] == ["PYSEC-1"]


def test_ai_explanation_is_included(client, seed_analysis):
    analysis_id = seed_analysis(
        [dict(tool="bandit", category="security", severity="high", rule_id="B602",
              ai_explanation="Because shell=True is risky.")]
    )

    finding = client.get(f"/analysis/{analysis_id}").json()["findings"][0]

    assert finding["ai_explanation"] == "Because shell=True is risky."


def test_findings_list_is_capped_at_200(client, seed_analysis):
    analysis_id = seed_analysis(
        [dict(tool="ruff", category="quality", severity="low", rule_id=f"R{i}") for i in range(250)]
    )

    body = client.get(f"/analysis/{analysis_id}").json()

    assert body["total_findings"] == 250
    assert len(body["findings"]) == 200