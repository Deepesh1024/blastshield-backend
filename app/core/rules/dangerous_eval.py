"""
Dangerous Eval Rule — Detects eval(), exec(), compile() with non-literal arguments.

Triggers when these functions are called with anything other than a string literal,
which indicates potential code injection.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "dangerous_eval"

DANGEROUS_FUNCTIONS = {"eval", "exec", "compile", "__import__"}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect dangerous eval/exec/compile calls."""
    violations: list[RuleViolation] = []

    all_funcs = list(module_ast.functions)
    for cls in module_ast.classes:
        all_funcs.extend(cls.methods)

    for func in all_funcs:
        if not func.body_source.strip():
            continue

        try:
            tree = ast.parse(func.body_source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            call_name = _extract_call_name(node.func)
            if call_name not in DANGEROUS_FUNCTIONS:
                continue

            # Check if all arguments are string literals (safe)
            all_literal = all(
                isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                for arg in node.args
            )

            if not all_literal or not node.args:
                violations.append(
                    RuleViolation(
                        rule_id=RULE_ID,
                        severity=Severity.CRITICAL,
                        file=module_ast.file_path,
                        line=func.line + getattr(node, "lineno", 1) - 1,
                        title=f"Dangerous '{call_name}()' with non-literal argument",
                        description=(
                            f"In function '{func.name}', '{call_name}()' is called "
                            f"with a dynamic (non-literal) argument. This enables "
                            f"arbitrary code execution. An attacker controlling the "
                            f"input can execute any Python code in the process."
                        ),
                        evidence=[
                            f"Function: {func.qualified_name or func.name}",
                            f"Dangerous call: {call_name}()",
                            f"Argument type: {'no args' if not node.args else 'dynamic expression'}",
                            "Non-literal arguments allow arbitrary code execution",
                        ],
                        affected_function=func.qualified_name or func.name,
                    )
                )

    return violations


def _extract_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
