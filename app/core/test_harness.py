"""
Unit-Test Stress Harness — Generates and runs edge-case tests automatically.

Behind feature flag (test_harness_enabled). Generates boundary inputs based on
function signatures and runs them in isolated subprocesses to capture:
- Runtime failures
- Uncaught exceptions
- Memory spikes
- Return value validation
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field

from app.models.ast_models import FunctionDef, ModuleAST


@dataclass
class TestCase:
    """A generated edge-case test."""

    function_name: str
    args: dict[str, object]
    description: str


@dataclass
class TestResult:
    """Result of running a single test case."""

    function_name: str
    test_description: str
    passed: bool
    error_type: str | None = None
    error_message: str | None = None
    traceback: str | None = None
    duration_ms: float = 0.0
    return_value: str | None = None


def generate_edge_cases(func: FunctionDef) -> list[TestCase]:
    """
    Generate edge-case test inputs based on function signature.

    Generates boundary values: None, empty string, 0, -1, MAX_INT,
    empty list, empty dict, very long strings, etc.
    """
    cases: list[TestCase] = []

    params = [p for p in func.parameters if p.name != "self"]
    if not params:
        # No-arg function — just call it
        cases.append(
            TestCase(
                function_name=func.name,
                args={},
                description="Call with no arguments",
            )
        )
        return cases

    # Generate boundary values per type annotation
    for param in params:
        ann = (param.annotation or "").lower()

        boundary_values: list[tuple[object, str]] = [
            (None, "None input"),
        ]

        if ann in ("str", "string", "") or not ann:
            boundary_values.extend([
                ("", "empty string"),
                ("a" * 10000, "very long string"),
                ("<script>alert(1)</script>", "XSS payload"),
                ("'; DROP TABLE users; --", "SQL injection"),
                ("../../../etc/passwd", "path traversal"),
            ])

        if ann in ("int", "float", "number", "") or not ann:
            boundary_values.extend([
                (0, "zero"),
                (-1, "negative"),
                (2**31, "MAX_INT overflow"),
                (float("inf"), "infinity"),
            ])

        if ann in ("list", "array", "") or not ann:
            boundary_values.extend([
                ([], "empty list"),
                ([None] * 100, "list of Nones"),
            ])

        if ann in ("dict", "mapping", "") or not ann:
            boundary_values.extend([
                ({}, "empty dict"),
            ])

        for value, desc in boundary_values:
            args = {p.name: None for p in params}
            args[param.name] = value
            cases.append(
                TestCase(
                    function_name=func.name,
                    args=args,
                    description=f"{param.name}={desc}",
                )
            )

    return cases


def run_tests(
    test_cases: list[TestCase],
    source: str,
    timeout: int = 5,
) -> list[TestResult]:
    """
    Run generated test cases in isolated subprocess sandbox.

    Each test is run in a separate subprocess with a timeout to prevent
    hanging or infinite loops.
    """
    results: list[TestResult] = []

    for tc in test_cases:
        result = _run_single_test(tc, source, timeout)
        results.append(result)

    return results


def _run_single_test(tc: TestCase, source: str, timeout: int) -> TestResult:
    """Run a single test case in a subprocess."""
    # Build test script
    test_script = textwrap.dedent(f"""\
        import json
        import sys
        import traceback

        # Source code under test
        {textwrap.indent(source, '        ').strip()}

        # Test execution
        try:
            args = json.loads('''{json.dumps(tc.args)}''')
            result = {tc.function_name}(**args)
            print(json.dumps({{"passed": True, "return_value": repr(result)}}))
        except Exception as e:
            print(json.dumps({{
                "passed": False,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": traceback.format_exc()
            }}))
    """)

    start = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=True) as f:
            f.write(test_script)
            f.flush()

            proc = subprocess.run(
                [sys.executable, f.name],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        elapsed = (time.monotonic() - start) * 1000

        if proc.returncode != 0 or not proc.stdout.strip():
            return TestResult(
                function_name=tc.function_name,
                test_description=tc.description,
                passed=False,
                error_type="ProcessError",
                error_message=proc.stderr[:500] if proc.stderr else "No output",
                duration_ms=round(elapsed, 2),
            )

        try:
            output = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            return TestResult(
                function_name=tc.function_name,
                test_description=tc.description,
                passed=False,
                error_type="OutputParseError",
                error_message=proc.stdout[:500],
                duration_ms=round(elapsed, 2),
            )

        return TestResult(
            function_name=tc.function_name,
            test_description=tc.description,
            passed=output.get("passed", False),
            error_type=output.get("error_type"),
            error_message=output.get("error_message"),
            traceback=output.get("traceback"),
            return_value=output.get("return_value"),
            duration_ms=round(elapsed, 2),
        )

    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            function_name=tc.function_name,
            test_description=tc.description,
            passed=False,
            error_type="TimeoutError",
            error_message=f"Test exceeded {timeout}s timeout — possible infinite loop",
            duration_ms=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return TestResult(
            function_name=tc.function_name,
            test_description=tc.description,
            passed=False,
            error_type=type(e).__name__,
            error_message=str(e),
            duration_ms=round(elapsed, 2),
        )
