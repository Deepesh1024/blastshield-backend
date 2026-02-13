"""
Data Flow Analyzer — Traces input→return propagation and detects flow issues.

Performs intra-function data flow analysis to detect:
- Nullable return contracts (function can return None without guard)
- Unguarded propagation of external input
- Cross-module mutation via global/shared state
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from app.models.ast_models import FunctionDef, ModuleAST


@dataclass
class DataFlowIssue:
    """A data flow problem detected by the analyzer."""

    issue_type: str  # 'nullable_return', 'unguarded_input', 'cross_module_mutation'
    file: str
    function: str
    line: int
    description: str
    evidence: list[str] = field(default_factory=list)


def analyze_data_flow(module_ast: ModuleAST) -> list[DataFlowIssue]:
    """
    Analyze data flow within a module.

    Checks each function for:
    1. Nullable return paths (can return None when annotation suggests otherwise)
    2. Unguarded external input propagation (parameters used directly in dangerous calls)
    3. Module-level mutable state mutation from within functions
    """
    issues: list[DataFlowIssue] = []

    all_funcs = list(module_ast.functions)
    for cls in module_ast.classes:
        all_funcs.extend(cls.methods)

    # Collect module-level mutable names
    mutable_module_vars: set[str] = set()
    for vm in module_ast.variable_mutations:
        if vm.scope == "module" and vm.target_type in ("list", "dict", "set"):
            mutable_module_vars.add(vm.name)

    for func in all_funcs:
        issues.extend(_check_nullable_return(func, module_ast.file_path))
        issues.extend(_check_unguarded_input(func, module_ast.file_path))
        issues.extend(
            _check_cross_module_mutation(func, mutable_module_vars, module_ast.file_path)
        )

    return issues


def _check_nullable_return(func: FunctionDef, file_path: str) -> list[DataFlowIssue]:
    """Detect functions that can implicitly return None."""
    issues: list[DataFlowIssue] = []

    if not func.body_source.strip():
        return issues

    try:
        tree = ast.parse(func.body_source)
    except SyntaxError:
        return issues

    # Find all return statements
    returns: list[ast.Return] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return):
            returns.append(node)

    if not returns:
        # No explicit return — function implicitly returns None
        if func.return_annotation and func.return_annotation not in ("None", "none", "NoneType"):
            issues.append(
                DataFlowIssue(
                    issue_type="nullable_return",
                    file=file_path,
                    function=func.qualified_name or func.name,
                    line=func.line,
                    description=(
                        f"Function '{func.name}' has return annotation '{func.return_annotation}' "
                        f"but has no explicit return statement (implicitly returns None)."
                    ),
                    evidence=[
                        f"Return annotation: {func.return_annotation}",
                        "No return statement found in function body",
                    ],
                )
            )
    else:
        # Check for return paths that return None or have no value
        for ret in returns:
            if ret.value is None:
                if func.return_annotation and func.return_annotation not in (
                    "None", "none", "NoneType", "Optional",
                ):
                    issues.append(
                        DataFlowIssue(
                            issue_type="nullable_return",
                            file=file_path,
                            function=func.qualified_name or func.name,
                            line=func.line + getattr(ret, "lineno", 1) - 1,
                            description=(
                                f"Function '{func.name}' returns None on some paths "
                                f"despite annotation '{func.return_annotation}'."
                            ),
                            evidence=[
                                f"Return annotation: {func.return_annotation}",
                                f"Bare 'return' at relative line {getattr(ret, 'lineno', '?')}",
                            ],
                        )
                    )

    return issues


def _check_unguarded_input(func: FunctionDef, file_path: str) -> list[DataFlowIssue]:
    """Detect function parameters used directly in dangerous operations."""
    issues: list[DataFlowIssue] = []

    if not func.body_source.strip():
        return issues

    param_names = {p.name for p in func.parameters if p.name != "self"}
    if not param_names:
        return issues

    dangerous_calls = {
        "eval", "exec", "compile", "os.system", "subprocess.run",
        "subprocess.call", "subprocess.Popen", "open",
    }

    try:
        tree = ast.parse(func.body_source)
    except SyntaxError:
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _extract_call_name(node.func)
            if call_name in dangerous_calls:
                # Check if any argument is a raw parameter
                for arg in node.args:
                    if isinstance(arg, ast.Name) and arg.id in param_names:
                        issues.append(
                            DataFlowIssue(
                                issue_type="unguarded_input",
                                file=file_path,
                                function=func.qualified_name or func.name,
                                line=func.line + getattr(node, "lineno", 1) - 1,
                                description=(
                                    f"Parameter '{arg.id}' is passed directly to "
                                    f"'{call_name}()' without validation or sanitization."
                                ),
                                evidence=[
                                    f"Parameter: {arg.id}",
                                    f"Dangerous call: {call_name}()",
                                    "No input validation detected before use",
                                ],
                            )
                        )
                # Check keyword args too
                for kw in node.keywords:
                    if isinstance(kw.value, ast.Name) and kw.value.id in param_names:
                        issues.append(
                            DataFlowIssue(
                                issue_type="unguarded_input",
                                file=file_path,
                                function=func.qualified_name or func.name,
                                line=func.line + getattr(node, "lineno", 1) - 1,
                                description=(
                                    f"Parameter '{kw.value.id}' is passed directly to "
                                    f"'{call_name}()' via keyword '{kw.arg}' without validation."
                                ),
                                evidence=[
                                    f"Parameter: {kw.value.id}",
                                    f"Dangerous call: {call_name}()",
                                    f"Keyword: {kw.arg}",
                                ],
                            )
                        )

    return issues


def _check_cross_module_mutation(
    func: FunctionDef, mutable_module_vars: set[str], file_path: str
) -> list[DataFlowIssue]:
    """Detect functions that mutate module-level mutable state."""
    issues: list[DataFlowIssue] = []

    for var_name in func.writes_globals:
        if var_name in mutable_module_vars:
            issues.append(
                DataFlowIssue(
                    issue_type="cross_module_mutation",
                    file=file_path,
                    function=func.qualified_name or func.name,
                    line=func.line,
                    description=(
                        f"Function '{func.name}' mutates module-level mutable "
                        f"variable '{var_name}'. This can cause race conditions "
                        f"in concurrent environments."
                    ),
                    evidence=[
                        f"Module-level mutable: {var_name}",
                        f"Mutated by: {func.name}",
                        f"Variable type: mutable container",
                    ],
                )
            )

    return issues


def _extract_call_name(node: ast.AST) -> str:
    """Extract function name from a call node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _extract_call_name(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    return ""
