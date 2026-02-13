"""
Rule Engine — Orchestrates all deterministic rules.

Runs all registered rules against parsed AST modules and call graphs.
No LLM involvement — pure deterministic analysis.
"""

from __future__ import annotations

import time
from typing import Callable

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleResult, RuleViolation

# Import all rule modules
from app.core.rules import (
    blocking_io_in_async,
    dangerous_eval,
    missing_await,
    missing_exception_boundary,
    race_condition,
    retry_without_backoff,
    shared_mutable_state,
    unsanitized_io,
)

# Type for a rule check function
RuleCheckFn = Callable[[ModuleAST, CallGraph | None], list[RuleViolation]]

# Registry of all deterministic rules
RULE_REGISTRY: dict[str, RuleCheckFn] = {
    race_condition.RULE_ID: race_condition.check,
    missing_await.RULE_ID: missing_await.check,
    unsanitized_io.RULE_ID: unsanitized_io.check,
    dangerous_eval.RULE_ID: dangerous_eval.check,
    shared_mutable_state.RULE_ID: shared_mutable_state.check,
    missing_exception_boundary.RULE_ID: missing_exception_boundary.check,
    retry_without_backoff.RULE_ID: retry_without_backoff.check,
    blocking_io_in_async.RULE_ID: blocking_io_in_async.check,
}


class RuleEngine:
    """
    Deterministic rule engine.

    Runs all registered rules against ModuleAST objects.
    Rules are pure functions — no LLM, no network, no randomness.
    """

    def __init__(self, rules: dict[str, RuleCheckFn] | None = None) -> None:
        self.rules = rules or RULE_REGISTRY

    def run(
        self,
        modules: dict[str, ModuleAST],
        call_graph: CallGraph | None = None,
    ) -> RuleResult:
        """
        Run all rules against all modules.

        Args:
            modules: Dict mapping file_path -> ModuleAST.
            call_graph: Optional call graph for cross-module rules.

        Returns:
            RuleResult with all violations found.
        """
        start = time.monotonic()
        all_violations: list[RuleViolation] = []
        rules_executed: list[str] = []

        for rule_id, check_fn in self.rules.items():
            rules_executed.append(rule_id)
            for file_path, module_ast in modules.items():
                try:
                    violations = check_fn(module_ast, call_graph)
                    all_violations.extend(violations)
                except Exception as e:
                    # Rule failures should not crash the engine
                    all_violations.append(
                        RuleViolation(
                            rule_id=rule_id,
                            severity="low",
                            file=file_path,
                            line=0,
                            title=f"Rule '{rule_id}' internal error",
                            description=f"Rule execution failed: {e}",
                            evidence=[f"Exception: {type(e).__name__}: {e}"],
                        )
                    )

        elapsed = (time.monotonic() - start) * 1000

        return RuleResult(
            violations=all_violations,
            rules_executed=rules_executed,
            total_files_scanned=len(modules),
            scan_duration_ms=round(elapsed, 2),
        )

    def run_single_rule(
        self,
        rule_id: str,
        module_ast: ModuleAST,
        call_graph: CallGraph | None = None,
    ) -> list[RuleViolation]:
        """Run a single rule against a single module."""
        if rule_id not in self.rules:
            raise ValueError(f"Unknown rule: {rule_id}")
        return self.rules[rule_id](module_ast, call_graph)
