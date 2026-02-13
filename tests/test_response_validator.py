"""
Tests for Response Validator — verify LLM output validation.
"""

from app.llm.response_validator import validate_llm_response


def test_rejects_none_response():
    result = validate_llm_response(
        parsed=None,
        valid_file_paths=set(),
        valid_rule_ids=set(),
        violation_line_ranges={},
    )
    assert not result.valid
    assert len(result.errors) > 0


def test_accepts_valid_response():
    parsed = {
        "explanations": [
            {
                "violation_rule_id": "dangerous_eval",
                "natural_language_explanation": "Using eval is dangerous.",
                "production_risk_summary": "Code injection risk.",
                "patch_suggestions": [
                    {
                        "file": "test.py",
                        "start_line": 10,
                        "end_line": 12,
                        "new_code": "result = ast.literal_eval(code_string)",
                        "rationale": "Use safe alternative",
                    }
                ],
            }
        ],
        "blast_impact_summary": "Limited impact.",
        "overall_recommendation": "Fix before shipping.",
    }
    result = validate_llm_response(
        parsed=parsed,
        valid_file_paths={"test.py"},
        valid_rule_ids={"dangerous_eval"},
        violation_line_ranges={"dangerous_eval": (8, 14)},
    )
    assert result.valid
    assert result.response is not None


def test_rejects_hallucinated_rule_id():
    parsed = {
        "explanations": [
            {
                "violation_rule_id": "invented_rule",
                "natural_language_explanation": "Something made up.",
                "production_risk_summary": "Made up risk.",
                "patch_suggestions": [],
            }
        ],
    }
    result = validate_llm_response(
        parsed=parsed,
        valid_file_paths={"test.py"},
        valid_rule_ids={"dangerous_eval"},
        violation_line_ranges={},
    )
    assert not result.valid
    assert any("hallucinated" in e.lower() or "invented_rule" in e for e in result.errors)


def test_rejects_invalid_file_path():
    parsed = {
        "explanations": [
            {
                "violation_rule_id": "dangerous_eval",
                "natural_language_explanation": "Eval is bad.",
                "production_risk_summary": "Injection.",
                "patch_suggestions": [
                    {
                        "file": "/etc/passwd",
                        "start_line": 1,
                        "end_line": 1,
                        "new_code": "safe code",
                        "rationale": "fix",
                    }
                ],
            }
        ],
    }
    result = validate_llm_response(
        parsed=parsed,
        valid_file_paths={"test.py"},
        valid_rule_ids={"dangerous_eval"},
        violation_line_ranges={"dangerous_eval": (10, 12)},
    )
    assert not result.valid
    assert any("not in scan input" in e for e in result.errors)


def test_rejects_out_of_range_patch():
    parsed = {
        "explanations": [
            {
                "violation_rule_id": "dangerous_eval",
                "natural_language_explanation": "Eval is bad.",
                "production_risk_summary": "Injection.",
                "patch_suggestions": [
                    {
                        "file": "test.py",
                        "start_line": 1,
                        "end_line": 200,
                        "new_code": "completely rewritten file",
                        "rationale": "rewrote everything",
                    }
                ],
            }
        ],
    }
    result = validate_llm_response(
        parsed=parsed,
        valid_file_paths={"test.py"},
        valid_rule_ids={"dangerous_eval"},
        violation_line_ranges={"dangerous_eval": (10, 12)},
    )
    assert not result.valid
    assert any("outside tolerance" in e for e in result.errors)
