"""
Patch Applier — Applies validated patches to source code.

Operates on source strings (in-memory), not disk files.
BlastShield receives code via API, so patches are applied to source strings
and returned in the response.
"""

from __future__ import annotations

import ast
import logging
import textwrap

logger = logging.getLogger("blastshield.engine.patch_applier")


def apply_function_patch(
    source: str,
    target_function: str,
    new_function_code: str,
) -> str | None:
    """
    Replace a function in source code with new code.

    Args:
        source: Original full file source
        target_function: Name of the function to replace
        new_function_code: New function code (complete function definition)

    Returns:
        Patched source string, or None if function not found
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.error(f"Cannot parse source for patching: {e}")
        return None

    lines = source.splitlines(keepends=True)

    # Find the function node
    func_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == target_function:
                func_node = node
                break

    if func_node is None:
        logger.error(f"Function '{target_function}' not found in source")
        return None

    # Determine the start line (including decorators)
    start_line = func_node.lineno
    if func_node.decorator_list:
        start_line = func_node.decorator_list[0].lineno
    end_line = func_node.end_lineno or func_node.lineno

    # Determine the indentation of the original function
    original_indent = ""
    if start_line <= len(lines):
        original_line = lines[start_line - 1]
        original_indent = original_line[: len(original_line) - len(original_line.lstrip())]

    # Dedent the new code first, then re-indent to match original
    dedented_new = textwrap.dedent(new_function_code)
    if original_indent:
        indented_new = textwrap.indent(dedented_new.strip(), original_indent)
    else:
        indented_new = dedented_new.strip()

    # Ensure trailing newline
    if not indented_new.endswith("\n"):
        indented_new += "\n"

    # Replace the lines
    # Convert to 0-indexed
    before = lines[: start_line - 1]
    after = lines[end_line:]

    patched_source = "".join(before) + indented_new + "".join(after)

    # Validate the result parses
    try:
        ast.parse(patched_source)
    except SyntaxError as e:
        logger.error(f"Patched source has syntax error: {e}")
        return None

    logger.info(
        f"Applied patch to '{target_function}' "
        f"(lines {start_line}-{end_line} replaced)"
    )
    return patched_source


def apply_line_range_patch(
    source: str,
    start_line: int,
    end_line: int,
    new_code: str,
) -> str | None:
    """
    Replace a specific line range in source code.

    Args:
        source: Original full file source
        start_line: 1-indexed start line
        end_line: 1-indexed end line (inclusive)
        new_code: Replacement code

    Returns:
        Patched source string, or None on error
    """
    lines = source.splitlines(keepends=True)

    if start_line < 1 or end_line > len(lines) or start_line > end_line:
        logger.error(
            f"Invalid line range {start_line}-{end_line} "
            f"(file has {len(lines)} lines)"
        )
        return None

    # Determine indentation from the first replaced line
    original_line = lines[start_line - 1]
    indent = original_line[: len(original_line) - len(original_line.lstrip())]

    # Indent new code
    dedented = textwrap.dedent(new_code)
    indented = textwrap.indent(dedented.strip(), indent)
    if not indented.endswith("\n"):
        indented += "\n"

    before = lines[: start_line - 1]
    after = lines[end_line:]
    patched = "".join(before) + indented + "".join(after)

    try:
        ast.parse(patched)
    except SyntaxError as e:
        logger.error(f"Line range patch produced syntax error: {e}")
        return None

    return patched
