"""
Re-Scan Module — Re-runs the rule engine on patched source to verify fix.

After applying a patch:
1. Re-parse the patched source
2. Re-run rule engine
3. Confirm target rule is eliminated
4. Confirm no new critical/high violations
5. Compute new risk score
6. Return pass/fail verdict
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.ast_parser import parse_file
from app.core.rule_engine import RuleEngine
from app.core.risk_scorer import compute_risk_score
from app.models.ast_models import ModuleAST

logger = logging.getLogger("blastshield.engine.rescan")


@dataclass
class RescanResult:
    """Result of re-scanning patched code."""

    passed: bool = False
    target_rule_eliminated: bool = False
    new_violations_introduced: list[str] = field(default_factory=list)
    risk_score_before: int = 0
    risk_score_after: int = 0
    risk_increased: bool = False
    details: str = ""


def rescan_patched_source(
    patched_source: str,
    file_path: str,
    target_rule_id: str,
    original_risk_score: int,
    rule_engine: RuleEngine | None = None,
) -> RescanResult:
    """
    Re-scan patched source to verify the fix.

    Args:
        patched_source: The patched file source code
        file_path: File path for context
        target_rule_id: The rule ID that should be eliminated
        original_risk_score: Risk score before patching
        rule_engine: Optional RuleEngine instance (creates new if None)

    Returns:
        RescanResult with pass/fail verdict
    """
    engine = rule_engine or RuleEngine()
    result = RescanResult(risk_score_before=original_risk_score)

    # Step 1: Parse patched source
    try:
        module_ast = parse_file(patched_source, file_path)
    except Exception as e:
        result.details = f"Failed to parse patched source: {e}"
        logger.error(result.details)
        return result

    # Step 2: Run rule engine
    rule_result = engine.run({file_path: module_ast})

    # Step 3: Check if target rule is eliminated
    remaining_target = [
        v for v in rule_result.violations if v.rule_id == target_rule_id
    ]
    result.target_rule_eliminated = len(remaining_target) == 0

    if not result.target_rule_eliminated:
        result.details = (
            f"Target rule '{target_rule_id}' still present after patch "
            f"({len(remaining_target)} violation(s) remaining)"
        )
        logger.warning(result.details)

    # Step 4: Check for new critical/high violations
    new_critical_high = [
        v for v in rule_result.violations
        if v.rule_id != target_rule_id
        and (
            v.severity in ("critical", "high")
            or (hasattr(v.severity, "value") and v.severity.value in ("critical", "high"))
        )
    ]
    result.new_violations_introduced = [
        f"{v.rule_id}: {v.title}" for v in new_critical_high
    ]

    # Step 5: Compute new risk score
    risk_breakdown = compute_risk_score(rule_result)
    result.risk_score_after = risk_breakdown.total_score

    # Step 6: Determine pass/fail
    result.risk_increased = result.risk_score_after > original_risk_score

    result.passed = (
        result.target_rule_eliminated
        and not result.new_violations_introduced
        and not result.risk_increased
    )

    if result.passed:
        result.details = (
            f"Re-scan passed: rule '{target_rule_id}' eliminated, "
            f"risk {original_risk_score} → {result.risk_score_after}"
        )
        logger.info(result.details)
    else:
        if not result.details:
            parts = []
            if not result.target_rule_eliminated:
                parts.append("target rule not eliminated")
            if result.new_violations_introduced:
                parts.append(
                    f"{len(result.new_violations_introduced)} new critical/high violations"
                )
            if result.risk_increased:
                parts.append(
                    f"risk increased {original_risk_score} → {result.risk_score_after}"
                )
            result.details = f"Re-scan failed: {'; '.join(parts)}"
            logger.warning(result.details)

    return result
