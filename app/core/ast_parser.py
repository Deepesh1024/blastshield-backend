"""
AST Parser — Deterministic code structure extraction.

Parses Python source code using the built-in `ast` module and extracts
structured representations: functions, classes, imports, variable mutations,
async boundaries, and exception flow.

JS/TS support is deferred to a future phase (requires Node.js subprocess).
"""

from __future__ import annotations

import ast
import textwrap
from typing import Any

from app.models.ast_models import (
    AsyncBoundary,
    ClassDef,
    ExceptionFlow,
    FunctionDef,
    ImportNode,
    ModuleAST,
    Parameter,
    VariableMutation,
)


class _PythonVisitor(ast.NodeVisitor):
    """Walks a Python AST and collects structured information."""

    def __init__(self, source_lines: list[str], file_path: str) -> None:
        self.source_lines = source_lines
        self.file_path = file_path
        self.imports: list[ImportNode] = []
        self.functions: list[FunctionDef] = []
        self.classes: list[ClassDef] = []
        self.variable_mutations: list[VariableMutation] = []
        self.async_boundaries: list[AsyncBoundary] = []
        self.exception_flows: list[ExceptionFlow] = []
        self.module_level_names: list[str] = []

        # Stack to track current scope
        self._scope_stack: list[str] = []

    @property
    def _current_scope(self) -> str:
        return self._scope_stack[-1] if self._scope_stack else "module"

    def _get_source_segment(self, node: ast.AST) -> str:
        """Extract source lines for a node."""
        try:
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            return "\n".join(self.source_lines[start:end])
        except (IndexError, AttributeError):
            return ""

    def _extract_name(self, node: ast.AST) -> str:
        """Extract a string name from various AST node types."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value_name = self._extract_name(node.value)
            return f"{value_name}.{node.attr}" if value_name else node.attr
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.Subscript):
            return self._extract_name(node.value)
        return ""

    def _extract_calls(self, node: ast.AST) -> tuple[list[str], list[str]]:
        """Extract all function calls and awaited calls from a function body."""
        calls: list[str] = []
        awaits: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                name = self._extract_name(child.func)
                if name:
                    calls.append(name)
            if isinstance(child, ast.Await):
                if isinstance(child.value, ast.Call):
                    name = self._extract_name(child.value.func)
                    if name:
                        awaits.append(name)
        return calls, awaits

    def _extract_global_access(
        self, node: ast.AST, module_names: set[str]
    ) -> tuple[list[str], list[str]]:
        """Extract reads/writes to module-level names within a function."""
        reads: list[str] = []
        writes: list[str] = []
        # Collect names declared global or nonlocal
        declared_global: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Global):
                declared_global.update(child.names)

        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                if child.id in declared_global or child.id in module_names:
                    if isinstance(child.ctx, (ast.Store, ast.Del)):
                        writes.append(child.id)
                    elif isinstance(child.ctx, ast.Load):
                        reads.append(child.id)
        return list(set(reads)), list(set(writes))

    def _parse_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, class_name: str = ""
    ) -> FunctionDef:
        """Parse a function/method definition node."""
        is_async = isinstance(node, ast.AsyncFunctionDef)

        # Parameters
        params: list[Parameter] = []
        for arg in node.args.args:
            annotation = (
                self._extract_name(arg.annotation) if arg.annotation else None
            )
            params.append(Parameter(name=arg.arg, annotation=annotation))

        # Return annotation
        return_ann = (
            self._extract_name(node.returns) if node.returns else None
        )

        # Decorators
        decorators = [self._extract_name(d) for d in node.decorator_list]

        # Calls and awaits
        calls, awaits = self._extract_calls(node)

        # Exception info
        exceptions_raised: list[str] = []
        exceptions_caught: list[str] = []
        has_bare_except = False
        has_try_except = False
        for child in ast.walk(node):
            if isinstance(child, ast.Raise) and child.exc:
                exceptions_raised.append(self._extract_name(child.exc))
            if isinstance(child, ast.ExceptHandler):
                has_try_except = True
                if child.type:
                    exceptions_caught.append(self._extract_name(child.type))
                else:
                    has_bare_except = True

        qualified = f"{class_name}.{node.name}" if class_name else node.name

        return FunctionDef(
            name=node.name,
            qualified_name=qualified,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            is_async=is_async,
            decorators=decorators,
            parameters=params,
            return_annotation=return_ann,
            calls=calls,
            awaits=awaits,
            exceptions_raised=exceptions_raised,
            exceptions_caught=exceptions_caught,
            has_bare_except=has_bare_except,
            has_try_except=has_try_except,
            body_source=self._get_source_segment(node),
        )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self.imports.append(
                ImportNode(
                    module=alias.name,
                    names=[alias.name],
                    alias=alias.asname,
                    line=node.lineno,
                    is_from_import=False,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        names = [alias.name for alias in node.names]
        self.imports.append(
            ImportNode(
                module=module,
                names=names,
                alias=None,
                line=node.lineno,
                is_from_import=True,
            )
        )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        if not self._scope_stack:  # Module-level function
            func = self._parse_function(node)
            self.functions.append(func)
            self.module_level_names.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        if not self._scope_stack:  # Module-level async function
            func = self._parse_function(node)
            self.functions.append(func)
            self.module_level_names.append(node.name)
            self.async_boundaries.append(
                AsyncBoundary(
                    type="async_def", name=node.name, line=node.lineno
                )
            )
        # Walk for inner awaits
        for child in ast.walk(node):
            if isinstance(child, ast.Await):
                self.async_boundaries.append(
                    AsyncBoundary(
                        type="await",
                        name=self._extract_name(child.value) if isinstance(child.value, ast.Call) else "",
                        line=child.lineno,
                        enclosing_function=node.name,
                    )
                )
            elif isinstance(child, ast.AsyncFor):
                self.async_boundaries.append(
                    AsyncBoundary(
                        type="async_for", line=child.lineno, enclosing_function=node.name
                    )
                )
            elif isinstance(child, ast.AsyncWith):
                self.async_boundaries.append(
                    AsyncBoundary(
                        type="async_with", line=child.lineno, enclosing_function=node.name
                    )
                )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        bases = [self._extract_name(b) for b in node.bases]
        decorators = [self._extract_name(d) for d in node.decorator_list]

        methods: list[FunctionDef] = []
        class_vars: list[str] = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._parse_function(item, class_name=node.name))
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    name = self._extract_name(target)
                    if name:
                        class_vars.append(name)

        self.classes.append(
            ClassDef(
                name=node.name,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                bases=bases,
                methods=methods,
                class_variables=class_vars,
                decorators=decorators,
            )
        )
        self.module_level_names.append(node.name)
        # Don't generic_visit — we already handled children
        # self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        if not self._scope_stack:  # Module-level assignment
            for target in node.targets:
                name = self._extract_name(target)
                if name:
                    # Infer type from value
                    target_type = None
                    if isinstance(node.value, ast.List):
                        target_type = "list"
                    elif isinstance(node.value, ast.Dict):
                        target_type = "dict"
                    elif isinstance(node.value, ast.Set):
                        target_type = "set"
                    elif isinstance(node.value, ast.Call):
                        target_type = self._extract_name(node.value.func)

                    self.variable_mutations.append(
                        VariableMutation(
                            name=name,
                            line=node.lineno,
                            scope="module",
                            target_type=target_type,
                        )
                    )
                    self.module_level_names.append(name)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802
        name = self._extract_name(node.target)
        if name:
            self.variable_mutations.append(
                VariableMutation(
                    name=name,
                    line=node.lineno,
                    scope="module" if not self._scope_stack else "local",
                    is_augmented=True,
                )
            )
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
        for handler in node.handlers:
            exc_types: list[str] = []
            is_bare = handler.type is None
            if handler.type:
                exc_types.append(self._extract_name(handler.type))

            has_reraise = any(
                isinstance(child, ast.Raise) and child.exc is None
                for child in ast.walk(handler)
            )

            self.exception_flows.append(
                ExceptionFlow(
                    line=handler.lineno,
                    end_line=getattr(handler, "end_lineno", handler.lineno),
                    exception_types=exc_types,
                    is_bare_except=is_bare,
                    has_reraise=has_reraise,
                )
            )
        self.generic_visit(node)

    # Python 3.11+ ast.TryStar
    visit_TryStar = visit_Try


def parse_python(source: str, file_path: str = "<unknown>") -> ModuleAST:
    """
    Parse Python source code into a structured ModuleAST.

    Args:
        source: Python source code string.
        file_path: Path to the source file (for reference in output).

    Returns:
        ModuleAST with all extracted structure.
    """
    parse_errors: list[str] = []
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        parse_errors.append(f"SyntaxError at line {e.lineno}: {e.msg}")
        return ModuleAST(
            file_path=file_path,
            language="python",
            total_lines=source.count("\n") + 1,
            parse_errors=parse_errors,
        )

    lines = source.splitlines()
    visitor = _PythonVisitor(lines, file_path)
    visitor.visit(tree)

    return ModuleAST(
        file_path=file_path,
        language="python",
        imports=visitor.imports,
        functions=visitor.functions,
        classes=visitor.classes,
        variable_mutations=visitor.variable_mutations,
        async_boundaries=visitor.async_boundaries,
        exception_flows=visitor.exception_flows,
        module_level_names=list(set(visitor.module_level_names)),
        total_lines=len(lines),
        parse_errors=parse_errors,
    )


def parse_file(source: str, file_path: str) -> ModuleAST:
    """
    Parse a source file based on its extension.

    Currently supports Python (.py). JS/TS support deferred to future phase.
    """
    if file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
        # Deferred: JS/TS parsing would invoke Node.js subprocess
        return ModuleAST(
            file_path=file_path,
            language="javascript",
            total_lines=source.count("\n") + 1,
            parse_errors=["JS/TS AST parsing not yet implemented — falling back to rule-skip"],
        )
    # Default to Python
    return parse_python(source, file_path)
