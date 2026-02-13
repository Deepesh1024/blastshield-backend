"""
Unsanitized I/O Rule — Detects file writes and subprocess calls with user-derived input.

Triggers when open(), write(), or subprocess functions are called with arguments
that can be traced back to function parameters without validation.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "unsanitized_io"

DANGEROUS_IO_CALLS = {
    "open": Severity.HIGH,
    "os.open": Severity.HIGH,
    "os.remove": Severity.CRITICAL,
    "os.unlink": Severity.CRITICAL,
    "os.rmdir": Severity.CRITICAL,
    "os.makedirs": Severity.MEDIUM,
    "shutil.rmtree": Severity.CRITICAL,
    "shutil.copy": Severity.HIGH,
    "shutil.move": Severity.HIGH,
    "subprocess.run": Severity.CRITICAL,
    "subprocess.call": Severity.CRITICAL,
    "subprocess.Popen": Severity.CRITICAL,
    "os.system": Severity.CRITICAL,
}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect unsanitized I/O operations."""
    violations: list[RuleViolation] = []

    all_funcs = list(module_ast.functions)
    for cls in module_ast.classes:
        all_funcs.extend(cls.methods)

    for func in all_funcs:
        if not func.body_source.strip():
            continue

        param_names = {p.name for p in func.parameters if p.name != "self"}
        if not param_names:
            continue

        try:
            tree = ast.parse(func.body_source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            call_name = _extract_call_name(node.func)
            if call_name not in DANGEROUS_IO_CALLS:
                continue

            severity = DANGEROUS_IO_CALLS[call_name]

            # Check for parameter taint in args
            tainted_params: list[str] = []
            for arg in node.args:
                tainted = _find_tainted_names(arg, param_names)
                tainted_params.extend(tainted)
            for kw in node.keywords:
                tainted = _find_tainted_names(kw.value, param_names)
                tainted_params.extend(tainted)

            if tainted_params:
                violations.append(
                    RuleViolation(
                        rule_id=RULE_ID,
                        severity=severity,
                        file=module_ast.file_path,
                        line=func.line + getattr(node, "lineno", 1) - 1,
                        title=f"Unsanitized input in '{call_name}()' call",
                        description=(
                            f"In function '{func.name}', parameter(s) "
                            f"{', '.join(set(tainted_params))} flow directly into "
                            f"'{call_name}()' without sanitization. This enables "
                            f"path traversal, command injection, or arbitrary file operations."
                        ),
                        evidence=[
                            f"Function: {func.qualified_name or func.name}",
                            f"Dangerous call: {call_name}()",
                            f"Tainted parameters: {', '.join(set(tainted_params))}",
                            "No input validation or sanitization detected",
                        ],
                        affected_function=func.qualified_name or func.name,
                    )
                )

    return violations


def _extract_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _extract_call_name(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    return ""


def _find_tainted_names(node: ast.AST, param_names: set[str]) -> list[str]:
    """Find parameter names that flow into an expression."""
    tainted: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in param_names:
            tainted.append(child.id)
    return tainted
