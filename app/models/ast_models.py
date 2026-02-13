"""
AST Data Models — Structured representations of parsed code.

These models are the output of the AST parser and the input to
the call graph builder, data flow analyzer, and rule engine.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportNode(BaseModel):
    """A single import statement."""

    module: str = Field(..., description="Imported module name")
    names: list[str] = Field(default_factory=list, description="Imported names")
    alias: str | None = Field(default=None, description="Import alias (as ...)")
    line: int = Field(..., description="Source line number")
    is_from_import: bool = Field(default=False, description="True if 'from X import Y'")


class Parameter(BaseModel):
    """A function parameter."""

    name: str
    annotation: str | None = None
    default: str | None = None


class FunctionDef(BaseModel):
    """A function or method definition."""

    name: str
    qualified_name: str = Field(
        default="", description="Fully qualified name (module.class.func)"
    )
    line: int
    end_line: int
    is_async: bool = False
    decorators: list[str] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    return_annotation: str | None = None
    calls: list[str] = Field(
        default_factory=list, description="Names of functions/methods called within"
    )
    awaits: list[str] = Field(
        default_factory=list, description="Names of awaited calls"
    )
    exceptions_raised: list[str] = Field(default_factory=list)
    exceptions_caught: list[str] = Field(default_factory=list)
    has_bare_except: bool = False
    has_try_except: bool = False
    reads_globals: list[str] = Field(
        default_factory=list, description="Global/module-level names read"
    )
    writes_globals: list[str] = Field(
        default_factory=list, description="Global/module-level names written"
    )
    body_source: str = Field(default="", description="Raw source of function body")


class ClassDef(BaseModel):
    """A class definition."""

    name: str
    line: int
    end_line: int
    bases: list[str] = Field(default_factory=list)
    methods: list[FunctionDef] = Field(default_factory=list)
    class_variables: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)


class VariableMutation(BaseModel):
    """A variable assignment or mutation."""

    name: str
    line: int
    scope: str = Field(
        default="local", description="Scope: 'local', 'global', 'class', 'module'"
    )
    is_augmented: bool = Field(
        default=False, description="True for +=, -=, etc."
    )
    target_type: str | None = Field(
        default=None, description="Inferred type of target (list, dict, etc.)"
    )


class AsyncBoundary(BaseModel):
    """An async boundary in the code."""

    type: str = Field(
        ..., description="Type: 'async_def', 'await', 'async_for', 'async_with'"
    )
    name: str = Field(default="", description="Associated name")
    line: int = Field(..., description="Source line number")
    enclosing_function: str = Field(
        default="", description="Name of the enclosing function"
    )


class ExceptionFlow(BaseModel):
    """An exception handler block."""

    line: int
    end_line: int
    exception_types: list[str] = Field(
        default_factory=list, description="Caught exception types"
    )
    is_bare_except: bool = False
    enclosing_function: str = ""
    has_reraise: bool = False


class ModuleAST(BaseModel):
    """Complete structured representation of a parsed module."""

    file_path: str
    language: str = Field(default="python", description="'python' or 'javascript'")
    imports: list[ImportNode] = Field(default_factory=list)
    functions: list[FunctionDef] = Field(default_factory=list)
    classes: list[ClassDef] = Field(default_factory=list)
    variable_mutations: list[VariableMutation] = Field(default_factory=list)
    async_boundaries: list[AsyncBoundary] = Field(default_factory=list)
    exception_flows: list[ExceptionFlow] = Field(default_factory=list)
    module_level_names: list[str] = Field(
        default_factory=list,
        description="All names defined at module level (vars, funcs, classes)",
    )
    total_lines: int = 0
    parse_errors: list[str] = Field(
        default_factory=list, description="Non-fatal parse warnings"
    )
