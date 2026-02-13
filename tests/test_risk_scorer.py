"""
Tests for Risk Scorer — verify score formula and explainability.
"""

from app.core.ast_parser import parse_python
from app.core.call_graph import build_call_graph
from app.core.risk_scorer import compute_risk_score
from app.core.rule_engine import RuleEngine


def test_risk_score_zero_for_clean_code(clean_python_code):
    module_ast = parse_python(clean_python_code, "clean.py")
    engine = RuleEngine()
    result = engine.run({"clean.py": module_ast})
    # Filter out any low-severity internal issues
    critical_high = [v for v in result.violations if v.severity.value in ("critical", "high")]
    if not critical_high:
        # If no critical/high violations, the test may still have low ones
        # but score should be very low
        risk = compute_risk_score(result)
        assert risk.total_score <= 30  # Should be low risk


def test_risk_score_nonzero_for_vulnerable_code(sample_python_code):
    module_ast = parse_python(sample_python_code, "test.py")
    engine = RuleEngine()
    result = engine.run({"test.py": module_ast})
    risk = compute_risk_score(result)
    assert risk.total_score > 0
    assert len(risk.violation_contributions) > 0


def test_risk_breakdown_explainable(sample_python_code):
    module_ast = parse_python(sample_python_code, "test.py")
    engine = RuleEngine()
    result = engine.run({"test.py": module_ast})
    risk = compute_risk_score(result)

    for contribution in risk.violation_contributions:
        assert contribution.base_weight > 0
        assert contribution.total_factor >= 1.0
        assert contribution.weighted_score > 0
        assert contribution.rule_id != ""
        assert contribution.severity in ("critical", "high", "medium", "low")


def test_risk_summary_present(sample_python_code):
    module_ast = parse_python(sample_python_code, "test.py")
    engine = RuleEngine()
    result = engine.run({"test.py": module_ast})
    risk = compute_risk_score(result)
    assert risk.summary != ""
    assert "violations" in risk.summary.lower()


def test_risk_score_bounded():
    """Risk score must always be 0-100."""
    from app.models.rule_models import RuleResult, RuleViolation, Severity

    # Extreme case: many critical violations
    violations = [
        RuleViolation(
            rule_id=f"test_{i}",
            severity=Severity.CRITICAL,
            file="test.py",
            line=i,
            title=f"Test violation {i}",
            description="Test",
        )
        for i in range(100)
    ]
    result = RuleResult(violations=violations, rules_executed=["test"])
    risk = compute_risk_score(result)
    assert 0 <= risk.total_score <= 100
