from app import models, services


def finding(tool, rule="R1"):
    return dict(
        tool=tool, category="quality", severity="low",
        file_path="a.py", line=1, rule_id=rule, message="m",
    )


def ok(tool):
    return lambda repo_path: [finding(tool)]


def boom(repo_path):
    raise RuntimeError("boom")


def prepare(monkeypatch, session_factory, tools, clone=lambda url: "/fake/path"):
    monkeypatch.setattr(services, "SessionLocal", session_factory)
    monkeypatch.setattr(services, "clone_repo", clone)
    monkeypatch.setattr(services, "cleanup", lambda path: None)
    monkeypatch.setattr(services, "TOOLS", tools)
    monkeypatch.setattr(services, "explain_top_findings", lambda db, analysis_id: None)


def result(session_factory, analysis_id):
    db = session_factory()
    try:
        analysis = db.get(models.Analysis, analysis_id)
        rows = db.query(models.Finding).filter_by(analysis_id=analysis_id).all()
        return analysis.status, analysis.error, sorted((f.tool, f.rule_id) for f in rows)
    finally:
        db.close()


def test_all_tools_succeed_gives_completed(monkeypatch, session_factory, seed_analysis):
    prepare(monkeypatch, session_factory, [("ruff", ok("ruff")), ("bandit", ok("bandit"))])
    analysis_id = seed_analysis([], status="pending")

    services.run_analysis(analysis_id)

    status, error, rows = result(session_factory, analysis_id)
    assert status == "completed"
    assert error is None
    assert rows == [("bandit", "R1"), ("ruff", "R1")]


def test_one_failing_tool_gives_partial_and_keeps_other_findings(
    monkeypatch, session_factory, seed_analysis
):
    prepare(monkeypatch, session_factory, [("ruff", ok("ruff")), ("radon", boom)])
    analysis_id = seed_analysis([], status="pending")

    services.run_analysis(analysis_id)

    status, error, rows = result(session_factory, analysis_id)
    assert status == "partial"
    assert "radon: boom" in error
    assert rows == [("ruff", "R1")]


def test_every_tool_failing_gives_failed(monkeypatch, session_factory, seed_analysis):
    prepare(monkeypatch, session_factory, [("ruff", boom), ("radon", boom)])
    analysis_id = seed_analysis([], status="pending")

    services.run_analysis(analysis_id)

    status, error, rows = result(session_factory, analysis_id)
    assert status == "failed"
    assert "boom" in error
    assert rows == []


def test_clone_failure_gives_failed_with_message(monkeypatch, session_factory, seed_analysis):
    def bad_clone(url):
        raise RuntimeError("clone failed")

    prepare(monkeypatch, session_factory, [("ruff", ok("ruff"))], clone=bad_clone)
    analysis_id = seed_analysis([], status="pending")

    services.run_analysis(analysis_id)

    status, error, rows = result(session_factory, analysis_id)
    assert status == "failed"
    assert error == "clone failed"


# ---- AI explanation step -------------------------------------------------


def explained_rule_ids(session_factory, analysis_id):
    db = session_factory()
    try:
        rows = db.query(models.Finding).filter_by(analysis_id=analysis_id).all()
        return {f.rule_id for f in rows if f.ai_explanation}
    finally:
        db.close()


def test_only_the_top_ten_most_severe_findings_are_explained(
    monkeypatch, session_factory, seed_analysis
):
    monkeypatch.setattr(services.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(services, "explain_finding", lambda f: f"explained {f.rule_id}")
    highs = [dict(tool="bandit", category="security", severity="high", rule_id=f"H{i}") for i in range(3)]
    lows = [dict(tool="ruff", category="quality", severity="low", rule_id=f"L{i}") for i in range(9)]
    analysis_id = seed_analysis(lows + highs)

    db = session_factory()
    services.explain_top_findings(db, analysis_id)
    db.close()

    explained = explained_rule_ids(session_factory, analysis_id)
    assert len(explained) == 10
    assert {"H0", "H1", "H2"} <= explained


def test_existing_explanations_are_reused_not_regenerated(
    monkeypatch, session_factory, seed_analysis
):
    monkeypatch.setattr(services.time, "sleep", lambda seconds: None)
    calls = []

    def fake_explain(f):
        calls.append(f.rule_id)
        return "fresh"

    monkeypatch.setattr(services, "explain_finding", fake_explain)
    analysis_id = seed_analysis([
        dict(tool="bandit", category="security", severity="high", rule_id="OLD", ai_explanation="cached text"),
        dict(tool="bandit", category="security", severity="high", rule_id="NEW"),
    ])

    db = session_factory()
    services.explain_top_findings(db, analysis_id)
    db.close()

    assert calls == ["NEW"]
    db = session_factory()
    old = db.query(models.Finding).filter_by(rule_id="OLD").one()
    assert old.ai_explanation == "cached text"
    db.close()


def test_one_failed_explanation_does_not_stop_the_rest(
    monkeypatch, session_factory, seed_analysis
):
    monkeypatch.setattr(services.time, "sleep", lambda seconds: None)

    def flaky(f):
        if f.rule_id == "B602":
            raise RuntimeError("llm down")
        return f"explained {f.rule_id}"

    monkeypatch.setattr(services, "explain_finding", flaky)
    analysis_id = seed_analysis([
        dict(tool="bandit", category="security", severity="high", rule_id=rule)
        for rule in ("B602", "X1", "X2")
    ])

    db = session_factory()
    services.explain_top_findings(db, analysis_id)
    db.close()

    assert explained_rule_ids(session_factory, analysis_id) == {"X1", "X2"}