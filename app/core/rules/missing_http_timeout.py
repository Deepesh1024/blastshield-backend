"""
Missing HTTP Timeout Rule — Detects HTTP client calls without a timeout parameter.

HTTP calls without timeout will hang indefinitely if the remote server doesn't respond,
blocking threads/coroutines and eventually exhausting the process's resources.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "missing_http_timeout"

# HTTP client calls that must have a timeout parameter
HTTP_CALLS = {
    "requests.get", "requests.post", "requests.put", "requests.delete",
    "requests.patch", "requests.head", "requests.request",
    "httpx.get", "httpx.post", "httpx.put", "httpx.delete",
    "httpx.patch", "httpx.head", "httpx.request",
    "urllib.request.urlopen",
    "aiohttp.ClientSession.get", "aiohttp.ClientSession.post",
}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect HTTP calls missing a timeout parameter."""
    violations: list[RuleViolation] = []

    all_funcs = list(module_ast.functions)
    for cls in module_ast.classes:
        all_funcs.extend(cls.methods)

    for func in all_funcs:
        body = func.body_source.strip()
        if not body:
            continue

        try:
            tree = ast.parse(body)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            call_name = _extract_call_name(node.func)
            if call_name not in HTTP_CALLS:
                continue

            # Check if timeout is in keyword args
            has_timeout = any(
                kw.arg == "timeout" for kw in node.keywords
            )

            if not has_timeout:
                violations.append(
                    RuleViolation(
                        rule_id=RULE_ID,
                        severity=Severity.HIGH,
                        file=module_ast.file_path,
                        line=func.line + getattr(node, "lineno", 1) - 1,
                        title=f"Missing timeout in '{call_name}()' inside '{func.name}'",
                        description=(
                            f"'{call_name}()' in function '{func.name}' has no timeout "
                            f"parameter. Without a timeout, the call will hang indefinitely "
                            f"if the remote server doesn't respond, blocking the thread/coroutine "
                            f"and eventually exhausting process resources."
                        ),
                        evidence=[
                            f"Function: {func.qualified_name or func.name}",
                            f"HTTP call: {call_name}()",
                            "No timeout= parameter specified",
                            "Fix: Add timeout=10 (or appropriate value) to the call",
                        ],
                        affected_function=func.qualified_name or func.name,
                        metadata={"failure_class": "resource_exhaustion"},
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
