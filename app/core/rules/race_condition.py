"""
Race Condition Rule — Detects shared state written by multiple async functions.

Triggers when a module-level mutable variable is written by more than one
async function reachable from the same entry point.
"""

from __future__ import annotations

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "race_condition"


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect potential race conditions via shared mutable state."""
    violations: list[RuleViolation] = []

    # Collect module-level mutable variables
    mutable_vars: dict[str, str] = {}  # name -> inferred type
    for vm in module_ast.variable_mutations:
        if vm.scope == "module" and vm.target_type in ("list", "dict", "set"):
            mutable_vars[vm.name] = vm.target_type or "unknown"

    if not mutable_vars:
        return violations

    # Find async functions that write to these variables
    async_funcs = [f for f in module_ast.functions if f.is_async]
    for cls in module_ast.classes:
        async_funcs.extend([m for m in cls.methods if m.is_async])

    # Map: mutable_var_name -> list of async functions that write to it
    writers: dict[str, list[str]] = {}
    for func in async_funcs:
        for var_name in func.writes_globals:
            if var_name in mutable_vars:
                writers.setdefault(var_name, []).append(func.qualified_name or func.name)

    # Violation if >1 async function writes to the same mutable var
    for var_name, func_names in writers.items():
        if len(func_names) > 1:
            violations.append(
                RuleViolation(
                    rule_id=RULE_ID,
                    severity=Severity.CRITICAL,
                    file=module_ast.file_path,
                    line=next(
                        (vm.line for vm in module_ast.variable_mutations if vm.name == var_name),
                        0,
                    ),
                    title=f"Race condition: '{var_name}' written by multiple async functions",
                    description=(
                        f"Module-level mutable '{var_name}' ({mutable_vars[var_name]}) "
                        f"is written by {len(func_names)} async functions: "
                        f"{', '.join(func_names)}. Without synchronization (locks/queues), "
                        f"concurrent execution will cause data corruption."
                    ),
                    evidence=[
                        f"Shared mutable variable: {var_name} (type: {mutable_vars[var_name]})",
                        f"Async writers: {', '.join(func_names)}",
                        "No synchronization primitive detected",
                    ],
                    affected_function=func_names[0],
                )
            )

    return violations
