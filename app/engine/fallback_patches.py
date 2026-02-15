"""
Deterministic Fallback Patches — Concrete code templates for known rules.

When LLM fails or is unavailable, these templates generate actual runnable
code patches (not TODO comments) for known rule violations.
"""

from __future__ import annotations

import ast
import logging
import textwrap

logger = logging.getLogger("blastshield.engine.fallback_patches")


# ── Template-based patch generators ──

def generate_fallback_patch(
    rule_id: str,
    function_source: str,
    function_name: str,
) -> str | None:
    """
    Generate a deterministic fallback patch for a known rule.

    Args:
        rule_id: Rule that triggered the violation
        function_source: Original function source code
        function_name: Name of the function

    Returns:
        Patched function code, or None if no template exists
    """
    generator = FALLBACK_GENERATORS.get(rule_id)
    if generator is None:
        logger.warning(f"No fallback template for rule '{rule_id}'")
        return None

    try:
        patched = generator(function_source, function_name)
        # Validate the result parses
        if patched:
            ast.parse(patched)
        return patched
    except SyntaxError as e:
        logger.error(f"Fallback patch for '{rule_id}' produced syntax error: {e}")
        return None
    except Exception as e:
        logger.error(f"Fallback patch generation failed for '{rule_id}': {e}")
        return None


def _patch_db_conn_per_request(source: str, func_name: str) -> str:
    """Replace raw DB connections with a connection pool pattern."""
    lines = source.splitlines()
    new_lines = []
    pool_added = False

    for line in lines:
        # Replace sqlite3.connect with pool usage
        if "sqlite3.connect" in line:
            indent = line[:len(line) - len(line.lstrip())]
            if not pool_added:
                new_lines.append(f"{indent}# Use connection pool instead of per-request connection")
                new_lines.append(f"{indent}conn = get_db_connection()  # from connection pool")
                pool_added = True
            continue
        # Replace psycopg2.connect
        if "psycopg2.connect" in line:
            indent = line[:len(line) - len(line.lstrip())]
            if not pool_added:
                new_lines.append(f"{indent}# Use connection pool instead of per-request connection")
                new_lines.append(f"{indent}conn = get_db_connection()  # from connection pool")
                pool_added = True
            continue
        # Replace pymysql.connect
        if "pymysql.connect" in line or "mysql.connector.connect" in line:
            indent = line[:len(line) - len(line.lstrip())]
            if not pool_added:
                new_lines.append(f"{indent}# Use connection pool instead of per-request connection")
                new_lines.append(f"{indent}conn = get_db_connection()  # from connection pool")
                pool_added = True
            continue
        new_lines.append(line)

    return "\n".join(new_lines)


def _patch_missing_http_timeout(source: str, func_name: str) -> str:
    """Add timeout parameter to HTTP calls."""
    lines = source.splitlines()
    new_lines = []

    http_methods = ["requests.get", "requests.post", "requests.put",
                    "requests.delete", "requests.patch", "requests.head",
                    "httpx.get", "httpx.post", "httpx.put",
                    "httpx.delete", "httpx.patch"]

    for line in lines:
        modified = line
        for method in http_methods:
            if method in line and "timeout" not in line:
                # Add timeout before closing paren
                if line.rstrip().endswith(")"):
                    modified = line.rstrip()[:-1] + ", timeout=10)"
                elif ")" in line:
                    modified = line.replace(")", ", timeout=10)", 1)
        new_lines.append(modified)

    return "\n".join(new_lines)


def _patch_blocking_io_in_async(source: str, func_name: str) -> str:
    """Replace blocking calls with async equivalents."""
    replacements = {
        "time.sleep(": "await asyncio.sleep(",
        "requests.get(": "await httpx.AsyncClient().get(",
        "requests.post(": "await httpx.AsyncClient().post(",
        "requests.put(": "await httpx.AsyncClient().put(",
        "requests.delete(": "await httpx.AsyncClient().delete(",
    }

    result = source
    for old, new in replacements.items():
        result = result.replace(old, new)

    return result


def _patch_missing_idempotency(source: str, func_name: str) -> str:
    """Add idempotency key check at the start of the function."""
    lines = source.splitlines()
    if not lines:
        return source

    # Find the function body start (after def line and docstring)
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            body_start = i + 1
            break

    # Skip docstring if present
    if body_start < len(lines):
        stripped = lines[body_start].strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            if stripped.count(quote) >= 2:
                body_start += 1
            else:
                for j in range(body_start + 1, len(lines)):
                    if quote in lines[j]:
                        body_start = j + 1
                        break

    # Determine indentation from the body
    indent = "    "
    if body_start < len(lines):
        body_line = lines[body_start]
        indent = body_line[:len(body_line) - len(body_line.lstrip())]

    idempotency_check = [
        f"{indent}# Idempotency guard — prevent duplicate processing",
        f"{indent}idempotency_key = request.headers.get('Idempotency-Key', '')",
        f"{indent}if idempotency_key:",
        f"{indent}    # Check if this request was already processed",
        f"{indent}    cached = await check_idempotency(idempotency_key)",
        f"{indent}    if cached is not None:",
        f"{indent}        return cached",
    ]

    new_lines = lines[:body_start] + idempotency_check + lines[body_start:]
    return "\n".join(new_lines)


def _patch_partial_txn_no_rollback(source: str, func_name: str) -> str:
    """Wrap DB operations in try/except with rollback."""
    lines = source.splitlines()
    new_lines = []
    in_function_body = False
    body_indent = "    "

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            new_lines.append(line)
            in_function_body = True
            # Determine body indent
            body_indent = line[:len(line) - len(line.lstrip())] + "    "
            continue

        if in_function_body and ("cursor.execute" in line or "session.add" in line):
            # Found a DB operation — wrap remaining body in try/except
            remaining_lines = lines[i:]
            new_lines.append(f"{body_indent}try:")
            for rem_line in remaining_lines:
                new_lines.append(f"    {rem_line}")
            new_lines.append(f"{body_indent}    conn.commit()")
            new_lines.append(f"{body_indent}except Exception as e:")
            new_lines.append(f"{body_indent}    conn.rollback()")
            new_lines.append(f"{body_indent}    raise")
            return "\n".join(new_lines)

        new_lines.append(line)

    return "\n".join(new_lines)


def _patch_missing_exception_boundary(source: str, func_name: str) -> str:
    """Wrap function body in try/except."""
    lines = source.splitlines()
    if not lines:
        return source

    # Find function body start
    body_start = 0
    func_indent = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("async def "):
            body_start = i + 1
            func_indent = line[:len(line) - len(line.lstrip())]
            break

    body_indent = func_indent + "    "

    # Skip docstring
    if body_start < len(lines):
        stripped = lines[body_start].strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            quote = stripped[:3]
            if stripped.count(quote) >= 2:
                body_start += 1
            else:
                for j in range(body_start + 1, len(lines)):
                    if quote in lines[j]:
                        body_start = j + 1
                        break

    # Wrap body in try/except
    header = lines[:body_start]
    body = lines[body_start:]

    wrapped = header + [f"{body_indent}try:"]
    for bline in body:
        wrapped.append(f"    {bline}")
    wrapped.append(f"{body_indent}except Exception as e:")
    wrapped.append(f"{body_indent}    logging.exception(f\"Error in {func_name}: {{e}}\")")
    wrapped.append(f"{body_indent}    raise")

    return "\n".join(wrapped)


# Registry of fallback generators by rule_id
FALLBACK_GENERATORS: dict[str, callable] = {
    "db_conn_per_request": _patch_db_conn_per_request,
    "missing_http_timeout": _patch_missing_http_timeout,
    "blocking_io_in_async": _patch_blocking_io_in_async,
    "missing_idempotency": _patch_missing_idempotency,
    "partial_txn_no_rollback": _patch_partial_txn_no_rollback,
    "missing_exception_boundary": _patch_missing_exception_boundary,
}
