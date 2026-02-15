"""
DB Connection Per Request Rule — Detects raw DB connections created inside request handlers.

Creating a new database connection for every request causes connection exhaustion
under load. Production systems must use connection pooling.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "db_conn_per_request"

# Database connection calls that should use pooling instead
DB_CONNECT_CALLS: dict[str, str] = {
    "sqlite3.connect": "Use a connection pool (e.g. sqlalchemy.create_engine with pool_size)",
    "psycopg2.connect": "Use psycopg2.pool.SimpleConnectionPool or SQLAlchemy pooling",
    "pymysql.connect": "Use SQLAlchemy connection pooling or DBUtils.PooledDB",
    "mysql.connector.connect": "Use mysql.connector.pooling.MySQLConnectionPool",
    "cx_Oracle.connect": "Use cx_Oracle.SessionPool",
    "pymongo.MongoClient": "Instantiate MongoClient once at module level, not per request",
    "redis.Redis": "Use a shared Redis connection pool (redis.ConnectionPool)",
    "redis.StrictRedis": "Use a shared Redis connection pool (redis.ConnectionPool)",
}

# Decorators that indicate a function is a request handler
HANDLER_DECORATORS = {
    "app.get", "app.post", "app.put", "app.delete", "app.patch",
    "router.get", "router.post", "router.put", "router.delete", "router.patch",
    "route", "get", "post", "put", "delete",
    "app.route", "blueprint.route",
}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect raw DB connections created inside request handler functions."""
    violations: list[RuleViolation] = []

    handler_funcs = []
    for func in module_ast.functions:
        if _is_handler(func.decorators) or _is_handler(func.calls):
            handler_funcs.append(func)
    for cls in module_ast.classes:
        for method in cls.methods:
            if _is_handler(method.decorators) or _is_handler(method.calls):
                handler_funcs.append(method)

    for func in handler_funcs:
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
            if call_name in DB_CONNECT_CALLS:
                fix = DB_CONNECT_CALLS[call_name]
                violations.append(
                    RuleViolation(
                        rule_id=RULE_ID,
                        severity=Severity.CRITICAL,
                        file=module_ast.file_path,
                        line=func.line + getattr(node, "lineno", 1) - 1,
                        title=f"DB connection '{call_name}()' created per request in '{func.name}'",
                        description=(
                            f"'{call_name}()' creates a new database connection on every "
                            f"request inside handler '{func.name}'. Under load this causes "
                            f"connection exhaustion, pool starvation, and service degradation. "
                            f"Fix: {fix}"
                        ),
                        evidence=[
                            f"Handler: {func.qualified_name or func.name}",
                            f"DB call: {call_name}()",
                            f"Fix: {fix}",
                            "Creates new connection per request — not pooled",
                        ],
                        affected_function=func.qualified_name or func.name,
                        metadata={"failure_class": "resource_exhaustion"},
                    )
                )

    return violations


def _is_handler(decorators: list[str]) -> bool:
    """Check if any decorator indicates a request handler."""
    for dec in decorators:
        dec_lower = dec.lower().strip("@")
        for handler_dec in HANDLER_DECORATORS:
            if handler_dec in dec_lower:
                return True
    return False


def _extract_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _extract_call_name(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    return ""
