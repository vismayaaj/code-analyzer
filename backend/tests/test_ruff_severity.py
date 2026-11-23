import pytest

from app.analyzers import ruff_runner


@pytest.mark.parametrize("code", ["F821", "F822", "F823", "F811"])
def test_rules_that_mean_real_bugs_are_high_severity(code):
    assert ruff_runner._classify(code) == ("bug", "high")


@pytest.mark.parametrize("code", ["F841", "F401", "F403", "F405", "F541", "B006", "B008"])
def test_other_bug_rules_are_medium_not_high(code):
    # F841 (unused variable) used to be high because it starts with "F8"
    assert ruff_runner._classify(code) == ("bug", "medium")


@pytest.mark.parametrize("code", ["E501", "W291", "SIM108", ""])
def test_style_rules_stay_low_quality(code):
    assert ruff_runner._classify(code) == ("quality", "low")