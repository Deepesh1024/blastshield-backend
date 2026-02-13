"""
Blocking I/O in Async Context Rule — Detects synchronous blocking calls inside async functions.

time.sleep(), synchronous requests.get(), and file I/O inside async def
will block the event loop, stalling all concurrent coroutines.
"""

from __future__ import annotations

import ast

from app.models.ast_models import ModuleAST
from app.models.graph_models import CallGraph
from app.models.rule_models import RuleViolation, Severity


RULE_ID = "blocking_io_in_async"

BLOCKING_CALLS = {
    "time.sleep": "Use asyncio.sleep() instead",
    "requests.get": "Use httpx.AsyncClient or aiohttp instead",
    "requests.post": "Use httpx.AsyncClient or aiohttp instead",
    "requests.put": "Use httpx.AsyncClient or aiohttp instead",
    "requests.delete": "Use httpx.AsyncClient or aiohttp instead",
    "requests.patch": "Use httpx.AsyncClient or aiohttp instead",
    "requests.head": "Use httpx.AsyncClient or aiohttp instead",
    "requests.request": "Use httpx.AsyncClient or aiohttp instead",
    "urllib.request.urlopen": "Use httpx.AsyncClient or aiohttp instead",
    "open": "Use aiofiles.open() instead",
    "input": "Use aioconsole.ainput() instead",
    "os.system": "Use asyncio.create_subprocess_shell() instead",
    "subprocess.run": "Use asyncio.create_subprocess_exec() instead",
    "subprocess.call": "Use asyncio.create_subprocess_exec() instead",
    "subprocess.check_output": "Use asyncio.create_subprocess_exec() instead",
}


def check(module_ast: ModuleAST, call_graph: CallGraph | None = None) -> list[RuleViolation]:
    """Detect blocking I/O calls inside async functions."""
    violations: list[RuleViolation] = []

    # Only check async functions
    async_funcs = [f for f in module_ast.functions if f.is_async]
    for cls in module_ast.classes:
        async_funcs.extend([m for m in cls.methods if m.is_async])

    for func in async_funcs:
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
            if call_name in BLOCKING_CALLS:
                fix_suggestion = BLOCKING_CALLS[call_name]
                violations.append(
                    RuleViolation(
                        rule_id=RULE_ID,
                        severity=Severity.HIGH,
                        file=module_ast.file_path,
                        line=func.line + getattr(node, "lineno", 1) - 1,
                        title=f"Blocking '{call_name}()' inside async function '{func.name}'",
                        description=(
                            f"'{call_name}()' is a synchronous blocking call used "
                            f"inside async function '{func.name}'. This blocks the "
                            f"entire event loop, stalling all concurrent coroutines. "
                            f"Fix: {fix_suggestion}"
                        ),
                        evidence=[
                            f"Async function: {func.qualified_name or func.name}",
                            f"Blocking call: {call_name}()",
                            f"Fix: {fix_suggestion}",
                            "Blocks event loop for all concurrent tasks",
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
