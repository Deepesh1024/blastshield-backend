"""
Risk Scoring Engine — Computes explainable risk scores from violations.

Risk Score = Σ(base_weight × factors) / max_possible × 100

Each violation's contribution is individually traced for explainability.
"""

from __future__ import annotations

from app.models.graph_models import CallGraph
from app.models.risk_models import RiskBreakdown, ViolationContribution
from app.models.rule_models import RuleResult, RuleViolation, Severity, SEVERITY_WEIGHTS


def compute_risk_score(
    rule_result: RuleResult,
    call_graph: CallGraph | None = None,
    test_failure_rule_ids: set[str] | None = None,
) -> RiskBreakdown:
    """
    Compute an explainable risk score from rule violations.

    Formula per violation:
        base_weight = severity_weight (critical=10, high=7, medium=4, low=1)
        factors = 1.0
            + 0.3 × (blast_radius / max_graph_depth)
            + 0.2 × (1 if mutates_shared_state)
            + 0.3 × (1 if test_failure_present)
            + 0.2 × (1 if async_boundary_crossing)

        weighted_score = base_weight × factors

    Total: risk_score = Σ weighted_scores / max_possible × 100, capped at 100

    Args:
        rule_result: Output from RuleEngine.run()
        call_graph: Optional call graph for blast radius computation
        test_failure_rule_ids: Set of rule_ids that also triggered test failures

    Returns:
        RiskBreakdown with per-violation contribution and total score.
    """
    test_failures = test_failure_rule_ids or set()
    violations = rule_result.violations

    if not violations:
        return RiskBreakdown(
            total_score=0,
            max_possible_score=0.0,
            violation_contributions=[],
            summary="No violations detected. Risk score is 0.",
        )

    max_graph_depth = call_graph.get_max_depth() if call_graph else 1
    if max_graph_depth == 0:
        max_graph_depth = 1

    contributions: list[ViolationContribution] = []
    total_weighted = 0.0

    for v in violations:
        base_weight = SEVERITY_WEIGHTS.get(v.severity, 1)

        # Blast radius factor
        blast_radius = 0
        if call_graph and v.graph_node_id and v.graph_node_id in call_graph.nodes:
            blast_radius = call_graph.get_blast_radius(v.graph_node_id)
        blast_factor = 0.3 * (blast_radius / max_graph_depth) if max_graph_depth > 0 else 0

        # State mutation factor
        state_mutation = 0.2 if v.rule_id in ("shared_mutable_state", "race_condition", "cross_module_mutation") else 0.0

        # Test failure factor
        test_factor = 0.3 if v.rule_id in test_failures else 0.0

        # Async boundary factor
        async_factor = 0.2 if v.rule_id in ("missing_await", "blocking_io_in_async", "race_condition") else 0.0

        total_factor = 1.0 + blast_factor + state_mutation + test_factor + async_factor
        weighted_score = base_weight * total_factor

        contributions.append(
            ViolationContribution(
                rule_id=v.rule_id,
                severity=v.severity.value if isinstance(v.severity, Severity) else v.severity,
                file=v.file,
                line=v.line,
                base_weight=base_weight,
                blast_radius_factor=round(blast_factor, 4),
                state_mutation_factor=round(state_mutation, 4),
                test_failure_factor=round(test_factor, 4),
                async_boundary_factor=round(async_factor, 4),
                total_factor=round(total_factor, 4),
                weighted_score=round(weighted_score, 4),
            )
        )
        total_weighted += weighted_score

    # Max possible: all violations at critical severity with all factors at 1
    max_possible = len(violations) * SEVERITY_WEIGHTS[Severity.CRITICAL] * 2.0  # max total_factor ~2.0
    if max_possible == 0:
        max_possible = 1

    raw_score = (total_weighted / max_possible) * 100
    final_score = min(100, max(0, int(round(raw_score))))

    # Summary
    critical_count = sum(1 for v in violations if v.severity in (Severity.CRITICAL, "critical"))
    high_count = sum(1 for v in violations if v.severity in (Severity.HIGH, "high"))
    medium_count = sum(1 for v in violations if v.severity in (Severity.MEDIUM, "medium"))
    low_count = sum(1 for v in violations if v.severity in (Severity.LOW, "low"))

    summary_parts = []
    if critical_count:
        summary_parts.append(f"{critical_count} critical")
    if high_count:
        summary_parts.append(f"{high_count} high")
    if medium_count:
        summary_parts.append(f"{medium_count} medium")
    if low_count:
        summary_parts.append(f"{low_count} low")

    summary = (
        f"Risk score {final_score}/100 based on {len(violations)} violations "
        f"({', '.join(summary_parts)}). "
        f"Weighted by blast radius, state mutation impact, test failures, "
        f"and async boundary crossings."
    )

    return RiskBreakdown(
        total_score=final_score,
        max_possible_score=round(max_possible, 2),
        violation_contributions=contributions,
        summary=summary,
    )
