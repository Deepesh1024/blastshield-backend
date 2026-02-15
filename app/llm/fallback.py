"""
Deterministic Fallback — Generates explanations and patches without LLM.

Used when:
- LLM fails or times out
- LLM response fails validation
- Risk score is below LLM invocation threshold

Template-based: each rule has pre-written explanation templates.
"""

from __future__ import annotations

from app.models.rule_models import RuleViolation
from app.models.scan_models import Issue, Patch


# Pre-written explanation templates per rule
RULE_TEMPLATES: dict[str, dict[str, str]] = {
    "race_condition": {
        "risk": (
            "Concurrent async functions writing to the same shared mutable state "
            "will corrupt data non-deterministically. This will cause intermittent "
            "bugs that are impossible to reproduce locally."
        ),
        "patch_hint": "Use asyncio.Lock() to synchronize access, or refactor to pass state via arguments.",
    },
    "missing_await": {
        "risk": (
            "The coroutine is created but never executed. The operation (database write, "
            "API call, file operation) will silently not happen, causing data loss."
        ),
        "patch_hint": "Add 'await' before the async function call.",
    },
    "unsanitized_io": {
        "risk": (
            "User-controlled input flows into file/system operations without sanitization. "
            "An attacker can perform path traversal, overwrite critical files, or execute "
            "arbitrary system commands."
        ),
        "patch_hint": "Validate and sanitize input: use os.path.basename(), restrict to allowed paths, and never pass raw user input to file/system operations.",
    },
    "dangerous_eval": {
        "risk": (
            "eval()/exec() with dynamic input enables arbitrary code execution. "
            "An attacker controlling the input can execute any Python code in the process, "
            "including reading secrets, modifying data, or spawning reverse shells."
        ),
        "patch_hint": "Replace eval/exec with ast.literal_eval() for data parsing, or use a proper parser/DSL.",
    },
    "shared_mutable_state": {
        "risk": (
            "Module-level mutable state creates implicit coupling between functions. "
            "In concurrent environments (threads, async, workers), this causes data races. "
            "In testing, it causes flaky tests due to shared state leaking between test cases."
        ),
        "patch_hint": "Encapsulate state in a class, pass as function arguments, or use thread-local storage.",
    },
    "missing_exception_boundary": {
        "risk": (
            "Unhandled exceptions in API handlers will return raw stack traces to clients "
            "(information leakage) or crash background workers without cleanup. "
            "In production, this causes 500 errors and service degradation."
        ),
        "patch_hint": "Wrap the handler body in try/except, log the error, and return a structured error response.",
    },
    "retry_without_backoff": {
        "risk": (
            "Retry loops without backoff will hammer the target service at full speed on failure. "
            "This causes cascading failures, IP bans, rate limit exhaustion, and amplifies outages."
        ),
        "patch_hint": "Add exponential backoff: time.sleep(2 ** attempt) between retries, with a max retry count.",
    },
    "blocking_io_in_async": {
        "risk": (
            "Blocking I/O inside async functions stalls the entire event loop. "
            "All concurrent coroutines (other API requests, background tasks) will freeze "
            "until the blocking call completes. This destroys concurrency and causes timeouts."
        ),
        "patch_hint": "Use async equivalents: asyncio.sleep(), httpx.AsyncClient, aiofiles.open(), asyncio.create_subprocess_exec().",
    },
    "db_conn_per_request": {
        "risk": (
            "Creating a new database connection for every request causes connection pool "
            "exhaustion under load. Connection establishment is expensive (TCP handshake, "
            "auth, TLS negotiation) and databases have connection limits."
        ),
        "patch_hint": "Use a connection pool: sqlalchemy.create_engine(pool_size=10), psycopg2.pool, or framework-provided pool.",
    },
    "missing_idempotency": {
        "risk": (
            "Non-idempotent write handlers cause duplicate records, double-charges, and "
            "data corruption when clients retry on timeout or network failure. This is "
            "especially dangerous for payment and order creation endpoints."
        ),
        "patch_hint": "Accept an Idempotency-Key header, check for prior execution, and return cached response on duplicate.",
    },
    "partial_txn_no_rollback": {
        "risk": (
            "DB operations without try/except + rollback leave partial transactions on failure. "
            "This corrupts data consistency, leaks DB connections, and can cause cascading "
            "failures in downstream systems."
        ),
        "patch_hint": "Wrap DB operations in try/except with rollback in except, or use a context manager (with conn:).",
    },
    "missing_http_timeout": {
        "risk": (
            "HTTP calls without a timeout will hang indefinitely if the remote server "
            "doesn't respond. This blocks threads/coroutines and eventually exhausts "
            "the process's resources, causing service unavailability."
        ),
        "patch_hint": "Add timeout=10 (or appropriate value) to all HTTP client calls.",
    },
}

DEFAULT_TEMPLATE = {
    "risk": "This violation may cause issues in production environments.",
    "patch_hint": "Review and fix the flagged code.",
}


def generate_fallback_issues(violations: list[RuleViolation]) -> list[Issue]:
    """
    Generate Issue objects from violations using deterministic templates.

    No LLM involved — pure template-based generation.
    """
    issues: list[Issue] = []

    for i, v in enumerate(violations):
        template = RULE_TEMPLATES.get(v.rule_id, DEFAULT_TEMPLATE)

        # Generate basic patch suggestion if possible
        patches: list[Patch] = []
        hint = template["patch_hint"]
        if v.line > 0:
            patches.append(
                Patch(
                    file=v.file,
                    start_line=v.line,
                    end_line=v.end_line or v.line,
                    new_code=f"# TODO: {hint}",
                )
            )

        issues.append(
            Issue(
                id=f"{v.rule_id}-{i + 1}",
                severity=v.severity.value if hasattr(v.severity, "value") else v.severity,
                file=v.file,
                line=v.line,
                rule_id=v.rule_id,
                issue=v.title,
                explanation=v.description,
                risk=template["risk"],
                evidence=v.evidence,
                patches=patches,
                testImpact=[],
            )
        )

    return issues
