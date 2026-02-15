"""
Missing Idempotency Rule — Detects POST/PUT/PATCH handlers that perform writes without idempotency guards.

Non-idempotent write handlers cause duplicate records, double-charges, and
data corruption when clients retry on timeout or network failure.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "missing_idempotency"

# Decorators indicating mutating endpoints
MUTATING_DECORATORS = {
    "app.post", "app.put", "app.patch",
    "router.post", "router.put", "router.patch",
    "post", "put", "patch",
    "blueprint.route",
}

# Calls that indicate a write operation
WRITE_CALLS = {
    "cursor.execute", "session.add", "session.commit", "session.flush",
    "db.session.add", "db.session.commit",
    "collection.insert_one", "collection.insert_many",
    "collection.update_one", "collection.update_many",
    "collection.replace_one",
    ".save", ".create", ".bulk_create",
    "requests.post", "requests.put", "requests.patch",
    "httpx.post", "httpx.put", "httpx.patch",
}

# Patterns indicating idempotency protection
IDEMPOTENCY_PATTERNS = {
    "idempotency_key", "idempotent", "if_not_exists",
    "get_or_create", "ON CONFLICT", "INSERT OR IGNORE",
    "upsert", "REPLACE INTO", "on_duplicate_key",
}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect mutating handlers lacking idempotency guards."""
    violations: list[RuleViolation] = []

    mutating_funcs = []
    for func in module_ast.functions:
        if _is_mutating_handler(func.decorators) or _is_mutating_handler(func.calls):
            mutating_funcs.append(func)
    for cls in module_ast.classes:
        for method in cls.methods:
            if _is_mutating_handler(method.decorators) or _is_mutating_handler(method.calls):
                mutating_funcs.append(method)

    for func in mutating_funcs:
        body = func.body_source.strip()
        if not body:
            continue

        # Check if function performs writes
        has_write = False
        for call_name in func.calls:
            for write_call in WRITE_CALLS:
                if write_call in call_name:
                    has_write = True
                    break
            if has_write:
                break

        # Also parse body for write calls
        if not has_write:
            try:
                tree = ast.parse(body)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        name = _extract_call_name(node.func)
                        for write_call in WRITE_CALLS:
                            if write_call in name:
                                has_write = True
                                break
                    if has_write:
                        break
            except SyntaxError:
                continue

        if not has_write:
            continue

        # Check for idempotency guards
        body_lower = body.lower()
        has_idempotency = any(pattern in body_lower for pattern in IDEMPOTENCY_PATTERNS)

        if not has_idempotency:
            violations.append(
                RuleViolation(
                    rule_id=RULE_ID,
                    severity=Severity.HIGH,
                    file=module_ast.file_path,
                    line=func.line,
                    end_line=func.end_line,
                    title=f"Missing idempotency guard in mutating handler '{func.name}'",
                    description=(
                        f"Handler '{func.name}' performs write operations (DB inserts, "
                        f"API calls) without an idempotency key or duplicate guard. "
                        f"Client retries on network failures will cause duplicate records, "
                        f"double-charges, or data corruption."
                    ),
                    evidence=[
                        f"Handler: {func.qualified_name or func.name}",
                        "Performs write operations without idempotency guard",
                        "Risk: duplicate records on client retry",
                        "Fix: Accept an idempotency key and check before executing write",
                    ],
                    affected_function=func.qualified_name or func.name,
                    metadata={"failure_class": "data_corruption"},
                )
            )

    return violations


def _is_mutating_handler(decorators: list[str]) -> bool:
    """Check if any decorator indicates a mutating handler."""
    for dec in decorators:
        dec_lower = dec.lower().strip("@")
        for mutating_dec in MUTATING_DECORATORS:
            if mutating_dec in dec_lower:
                return True
    return False


def _extract_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _extract_call_name(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    return ""
