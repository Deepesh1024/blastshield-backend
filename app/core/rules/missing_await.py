"""
Missing Await Rule — Detects async functions called without await.

Triggers when a coroutine call is made in a sync context without being awaited,
resulting in the coroutine being created but never executed.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "missing_await"


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect async functions called without await."""
    violations: list[RuleViolation] = []

    # Build set of known async function names in this module
    async_func_names: set[str] = set()
    for func in module_ast.functions:
        if func.is_async:
            async_func_names.add(func.name)
    for cls in module_ast.classes:
        for method in cls.methods:
            if method.is_async:
                async_func_names.add(method.name)
                async_func_names.add(f"{cls.name}.{method.name}")

    if not async_func_names:
        return violations

    # Also check cross-module async via call graph
    if call_graph:
        for node in call_graph.nodes.values():
            if node.is_async:
                async_func_names.add(node.function)

    # Check each function for calling async functions without await
    all_funcs = list(module_ast.functions)
    for cls in module_ast.classes:
        all_funcs.extend(cls.methods)

    for func in all_funcs:
        # Compare calls vs awaits
        awaited_names = set(func.awaits)
        for call_name in func.calls:
            # Get the base name (handle self.method → method)
            base_name = call_name.split(".")[-1] if "." in call_name else call_name
            if base_name in async_func_names or call_name in async_func_names:
                if call_name not in awaited_names and base_name not in awaited_names:
                    # This is an async function called without await
                    severity = Severity.HIGH if func.is_async else Severity.CRITICAL
                    violations.append(
                        RuleViolation(
                            rule_id=RULE_ID,
                            severity=severity,
                            file=module_ast.file_path,
                            line=func.line,
                            title=f"Async function '{call_name}' called without await",
                            description=(
                                f"In function '{func.name}', async function '{call_name}' "
                                f"is called without 'await'. The coroutine will be created "
                                f"but never executed, silently dropping the operation."
                            ),
                            evidence=[
                                f"Caller: {func.qualified_name or func.name} (async={func.is_async})",
                                f"Callee: {call_name} (async=True)",
                                "No 'await' keyword found for this call",
                                f"Awaited calls in this function: {list(awaited_names) or 'none'}",
                            ],
                            affected_function=func.qualified_name or func.name,
                        )
                    )

    return violations
