"""
Shared Mutable State Rule — Detects module-level mutable containers accessed by >1 function.

Module-level lists, dicts, and sets that are read/written by multiple functions
create implicit coupling and are unsafe under concurrent access.
"""

from __future__ import annotations

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "shared_mutable_state"


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect shared mutable state accessed by multiple functions."""
    violations: list[RuleViolation] = []

    # Collect module-level mutable variables
    mutable_vars: dict[str, int] = {}  # name -> line
    mutable_types: dict[str, str] = {}
    for vm in module_ast.variable_mutations:
        if vm.scope == "module" and vm.target_type in ("list", "dict", "set"):
            mutable_vars[vm.name] = vm.line
            mutable_types[vm.name] = vm.target_type or "mutable"

    if not mutable_vars:
        return violations

    # Map: var_name -> set of functions that access it (read or write)
    all_funcs = list(module_ast.functions)
    for cls in module_ast.classes:
        all_funcs.extend(cls.methods)

    accessors: dict[str, set[str]] = {}
    for func in all_funcs:
        for var_name in set(func.reads_globals) | set(func.writes_globals):
            if var_name in mutable_vars:
                accessors.setdefault(var_name, set()).add(
                    func.qualified_name or func.name
                )

    for var_name, func_set in accessors.items():
        if len(func_set) > 1:
            violations.append(
                RuleViolation(
                    rule_id=RULE_ID,
                    severity=Severity.HIGH,
                    file=module_ast.file_path,
                    line=mutable_vars[var_name],
                    title=f"Shared mutable state: '{var_name}' accessed by {len(func_set)} functions",
                    description=(
                        f"Module-level {mutable_types[var_name]} '{var_name}' is "
                        f"accessed by multiple functions: {', '.join(sorted(func_set))}. "
                        f"This creates implicit coupling and is unsafe under "
                        f"concurrent access (threads, async, multiprocessing)."
                    ),
                    evidence=[
                        f"Variable: {var_name} (type: {mutable_types[var_name]})",
                        f"Accessing functions: {', '.join(sorted(func_set))}",
                        f"Count: {len(func_set)} accessors",
                        "No encapsulation or thread-safety mechanism detected",
                    ],
                    affected_function=sorted(func_set)[0],
                )
            )

    return violations
