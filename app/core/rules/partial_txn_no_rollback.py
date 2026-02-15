"""
Partial Transaction Without Rollback Rule — Detects DB operations without proper
commit/rollback handling.

Executing DB writes without try/except with rollback leaves partial transactions
that corrupt data and leak connections.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "partial_txn_no_rollback"

# Calls that start/execute a transaction
TXN_CALLS = {
    "cursor.execute", "cursor.executemany", "cursor.executescript",
    "session.add", "session.flush", "session.bulk_save_objects",
    "db.session.add", "db.session.flush",
    "connection.execute",
}

# Calls that indicate proper transaction handling
COMMIT_CALLS = {"commit", "session.commit", "connection.commit", "db.session.commit"}
ROLLBACK_CALLS = {"rollback", "session.rollback", "connection.rollback", "db.session.rollback"}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect DB operations without proper commit/rollback handling."""
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

        # Find all transaction-starting calls
        has_txn_call = False
        txn_call_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _extract_call_name(node.func)
                for txn_call in TXN_CALLS:
                    if txn_call in name:
                        has_txn_call = True
                        txn_call_names.append(name)
                        break

        if not has_txn_call:
            continue

        # Check if they use context managers (with conn: / with session:)
        uses_context_manager = any(
            isinstance(node, ast.With) for node in ast.walk(tree)
        )

        # Check for try/except with rollback
        has_try_with_rollback = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                # Check if any handler calls rollback
                for handler in node.handlers:
                    for sub_node in ast.walk(handler):
                        if isinstance(sub_node, ast.Call):
                            name = _extract_call_name(sub_node.func)
                            if any(rb in name for rb in ROLLBACK_CALLS):
                                has_try_with_rollback = True
                                break

        # Check for commit without rollback protection
        has_commit = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _extract_call_name(node.func)
                if any(c in name for c in COMMIT_CALLS):
                    has_commit = True
                    break

        if not has_try_with_rollback and not uses_context_manager:
            severity = Severity.CRITICAL if not has_commit else Severity.HIGH
            violations.append(
                RuleViolation(
                    rule_id=RULE_ID,
                    severity=severity,
                    file=module_ast.file_path,
                    line=func.line,
                    end_line=func.end_line,
                    title=f"Partial transaction without rollback in '{func.name}'",
                    description=(
                        f"Function '{func.name}' executes DB operations "
                        f"({', '.join(txn_call_names[:3])}) without try/except + rollback "
                        f"handling or a context manager. On failure, partial writes remain, "
                        f"corrupting data and potentially leaking DB connections."
                    ),
                    evidence=[
                        f"Function: {func.qualified_name or func.name}",
                        f"DB operations: {', '.join(txn_call_names[:3])}",
                        f"Has commit: {has_commit}",
                        f"Has rollback: {has_try_with_rollback}",
                        "Fix: Wrap in try/except with rollback, or use a context manager",
                    ],
                    affected_function=func.qualified_name or func.name,
                    metadata={"failure_class": "data_corruption"},
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
