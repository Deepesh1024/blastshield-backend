"""
Missing Exception Boundary Rule — Detects async entry points and API handlers without try/except.

API handlers and async entry points should always have exception boundaries
to prevent unhandled exceptions from crashing the server or silently failing.
"""

from __future__ import annotations

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "missing_exception_boundary"

ENTRY_DECORATORS = {
    "app.route", "app.get", "app.post", "app.put", "app.delete", "app.patch",
    "router.get", "router.post", "router.put", "router.delete", "router.patch",
    "route", "get", "post", "put", "delete", "patch",
}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect entry points missing exception boundaries."""
    violations: list[RuleViolation] = []

    all_funcs = list(module_ast.functions)
    for cls in module_ast.classes:
        all_funcs.extend(cls.methods)

    for func in all_funcs:
        is_entry = any(
            d.lower() in ENTRY_DECORATORS for d in func.decorators
        ) or func.name in ("main", "__main__")

        # Also check async functions that look like handlers
        if not is_entry and func.is_async:
            # Async functions with HTTP-method-like names
            if any(
                func.name.startswith(prefix)
                for prefix in ("handle_", "on_", "process_", "endpoint_")
            ):
                is_entry = True

        if not is_entry:
            continue

        if not func.has_try_except:
            violations.append(
                RuleViolation(
                    rule_id=RULE_ID,
                    severity=Severity.HIGH,
                    file=module_ast.file_path,
                    line=func.line,
                    title=f"Missing exception boundary in entry point '{func.name}'",
                    description=(
                        f"Entry point '{func.name}' has no try/except block. "
                        f"Unhandled exceptions will propagate to the framework, "
                        f"potentially returning 500 errors with stack traces "
                        f"(information leakage) or crashing background workers."
                    ),
                    evidence=[
                        f"Function: {func.qualified_name or func.name}",
                        f"Decorators: {func.decorators or 'none'}",
                        f"Async: {func.is_async}",
                        "No try/except block found in function body",
                    ],
                    affected_function=func.qualified_name or func.name,
                )
            )

    return violations
