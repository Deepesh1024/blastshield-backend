"""
AST Validator — Structural validation of LLM-generated patches.

Before any patch is applied, this module performs 7 deterministic checks:
1. Code parses successfully (ast.parse)
2. Function name unchanged
3. Route decorator unchanged
4. No new global statements
5. No forbidden imports
6. No new blocking calls in async context
7. No deletion of critical lines (return statements, exception handlers)

If any check fails → patch is rejected.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("blastshield.engine.ast_validator")

# Imports that are never allowed in patches
FORBIDDEN_IMPORTS = {
    "os.system", "subprocess", "eval", "exec", "compile",
    "__import__", "importlib", "ctypes", "pickle",
}

# Blocking calls that should never appear in async functions
BLOCKING_CALLS = {
    "time.sleep", "requests.get", "requests.post", "requests.put",
    "requests.delete", "requests.patch", "requests.head",
    "open", "input", "os.system", "subprocess.run",
    "subprocess.call", "subprocess.check_output",
}


@dataclass
class ValidationVerdict:
    """Result of AST validation."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        self.valid = False
        self.errors.append(error)


def validate_patch_ast(
    original_source: str,
    patched_source: str,
    target_function: str,
    is_async: bool = False,
    original_decorators: list[str] | None = None,
) -> ValidationVerdict:
    """
    Validate a patch using AST-based structural checks.

    Args:
        original_source: The original full file source code
        patched_source: The patched full file source code
        target_function: Name of the function being patched
        is_async: Whether the target function is async
        original_decorators: Decorators on the original function

    Returns:
        ValidationVerdict with pass/fail and error list
    """
    verdict = ValidationVerdict()

    # ── Check 1: Code parses successfully ──
    try:
        patched_tree = ast.parse(patched_source)
    except SyntaxError as e:
        verdict.add_error(f"Patched code has syntax error: {e}")
        return verdict

    try:
        original_tree = ast.parse(original_source)
    except SyntaxError:
        # If original doesn't parse, we can't compare
        return verdict

    # ── Check 2: Function name unchanged ──
    original_funcs = _get_function_names(original_tree)
    patched_funcs = _get_function_names(patched_tree)

    if target_function in original_funcs and target_function not in patched_funcs:
        verdict.add_error(
            f"Function '{target_function}' was renamed or removed in patch"
        )

    # ── Check 3: Route decorator unchanged ──
    if original_decorators:
        patched_func_node = _find_function(patched_tree, target_function)
        if patched_func_node:
            patched_decs = _get_decorator_names(patched_func_node)
            for orig_dec in original_decorators:
                if _is_route_decorator(orig_dec) and orig_dec not in patched_decs:
                    verdict.add_error(
                        f"Route decorator '{orig_dec}' was modified or removed"
                    )

    # ── Check 4: No new global statements ──
    original_globals = _count_global_statements(original_tree)
    patched_globals = _count_global_statements(patched_tree)
    if patched_globals > original_globals:
        verdict.add_error(
            f"Patch introduces {patched_globals - original_globals} new global statement(s)"
        )

    # ── Check 5: No forbidden imports ──
    original_imports = _get_imports(original_tree)
    patched_imports = _get_imports(patched_tree)
    new_imports = patched_imports - original_imports
    for imp in new_imports:
        for forbidden in FORBIDDEN_IMPORTS:
            if forbidden in imp:
                verdict.add_error(f"Patch adds forbidden import: '{imp}'")

    # ── Check 6: No new blocking calls in async context ──
    if is_async:
        patched_func_node = _find_function(patched_tree, target_function)
        if patched_func_node:
            blocking = _find_blocking_calls(patched_func_node)
            if blocking:
                verdict.add_error(
                    f"Patch introduces blocking calls in async function: {blocking}"
                )

    # ── Check 7: No deletion of critical lines ──
    original_func = _find_function(original_tree, target_function)
    patched_func = _find_function(patched_tree, target_function)
    if original_func and patched_func:
        orig_returns = _count_return_statements(original_func)
        patched_returns = _count_return_statements(patched_func)
        if patched_returns < orig_returns:
            verdict.add_error(
                f"Patch removes {orig_returns - patched_returns} return statement(s)"
            )

        orig_handlers = _count_exception_handlers(original_func)
        patched_handlers = _count_exception_handlers(patched_func)
        if patched_handlers < orig_handlers:
            verdict.add_error(
                f"Patch removes {orig_handlers - patched_handlers} exception handler(s)"
            )

    if verdict.valid:
        logger.info(f"AST validation passed for function '{target_function}'")
    else:
        logger.warning(
            f"AST validation failed for '{target_function}': {verdict.errors}"
        )

    return verdict


# ── Helper functions ──


def _get_function_names(tree: ast.Module) -> set[str]:
    """Get all function names defined at any level."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def _find_function(
    tree: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Find a function definition by name."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node
    return None


def _get_decorator_names(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract decorator names from a function node."""
    decorators = []
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(_attr_to_str(dec))
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                decorators.append(_attr_to_str(dec.func))
    return decorators


def _is_route_decorator(name: str) -> bool:
    """Check if a decorator name looks like a route decorator."""
    route_keywords = {"route", "get", "post", "put", "delete", "patch", "head"}
    parts = name.lower().split(".")
    return any(part in route_keywords for part in parts)


def _count_global_statements(tree: ast.Module) -> int:
    """Count the number of 'global' statements."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            count += 1
    return count


def _get_imports(tree: ast.Module) -> set[str]:
    """Get all import module names."""
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


def _find_blocking_calls(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Find blocking calls inside a function node."""
    found = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            name = _call_to_str(node.func)
            if name in BLOCKING_CALLS:
                found.append(name)
    return found


def _count_return_statements(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count return statements in a function."""
    count = 0
    for node in ast.walk(func_node):
        if isinstance(node, ast.Return):
            count += 1
    return count


def _count_exception_handlers(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> int:
    """Count exception handler blocks."""
    count = 0
    for node in ast.walk(func_node):
        if isinstance(node, ast.ExceptHandler):
            count += 1
    return count


def _attr_to_str(node: ast.Attribute) -> str:
    """Convert an Attribute node to a dotted string."""
    if isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    if isinstance(node.value, ast.Attribute):
        return f"{_attr_to_str(node.value)}.{node.attr}"
    return node.attr


def _call_to_str(node: ast.AST) -> str:
    """Convert a Call.func node to a string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _call_to_str(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    return ""
