"""
Retry Without Backoff Rule — Detects retry/loop patterns calling APIs without exponential backoff.

Loops that contain network/API calls without sleep or backoff logic will
hammer external services and cause cascading failures.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "retry_without_backoff"

NETWORK_CALLS = {
    "requests.get", "requests.post", "requests.put", "requests.delete",
    "requests.patch", "requests.head", "requests.request",
    "httpx.get", "httpx.post", "httpx.put", "httpx.delete",
    "httpx.request", "httpx.AsyncClient",
    "aiohttp.ClientSession", "urllib.request.urlopen",
    "client.chat.completions.create",  # Groq / OpenAI SDK
    "openai.ChatCompletion.create",
}

BACKOFF_INDICATORS = {
    "time.sleep", "asyncio.sleep", "sleep",
    "backoff", "tenacity", "retry", "exponential_backoff",
}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect retry loops without backoff."""
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

        # Find loops (for/while)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                continue

            # Check if loop body contains a network call
            has_network_call = False
            network_call_name = ""
            has_backoff = False

            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    call_name = _extract_call_name(child.func)
                    if call_name in NETWORK_CALLS or any(
                        nc in call_name for nc in NETWORK_CALLS
                    ):
                        has_network_call = True
                        network_call_name = call_name
                    if call_name in BACKOFF_INDICATORS or any(
                        bi in call_name for bi in BACKOFF_INDICATORS
                    ):
                        has_backoff = True

            if has_network_call and not has_backoff:
                violations.append(
                    RuleViolation(
                        rule_id=RULE_ID,
                        severity=Severity.HIGH,
                        file=module_ast.file_path,
                        line=func.line + getattr(node, "lineno", 1) - 1,
                        title=f"Retry loop without backoff calling '{network_call_name}'",
                        description=(
                            f"In function '{func.name}', a loop makes network calls "
                            f"to '{network_call_name}' without any sleep/backoff logic. "
                            f"On failure, this will immediately retry at full speed, "
                            f"overwhelming the target service and causing cascading failures."
                        ),
                        evidence=[
                            f"Function: {func.qualified_name or func.name}",
                            f"Loop type: {type(node).__name__}",
                            f"Network call: {network_call_name}",
                            "No time.sleep(), asyncio.sleep(), or backoff decorator detected",
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
