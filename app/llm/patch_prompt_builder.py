"""
Patch Prompt Builder — Builds structured prompts for LLM patch generation.

Unlike the general prompt builder, this produces prompts specifically for
generating function-level code patches with strict constraints.
"""

from __future__ import annotations

import json

from app.models.rule_models import RuleViolation


PATCH_SYSTEM_PROMPT = """\
You are BlastShield Patch Engine, a code repair assistant that generates MINIMAL, SAFE patches.

You receive a single rule violation detected by the deterministic engine, along with the
source code of the affected function. Your task: generate a corrected version of ONLY the
affected function.

STRICT CONSTRAINTS — VIOLATION OF ANY CONSTRAINT MEANS REJECTION:
1. PRESERVE the function signature exactly (name, parameters, type hints, return type)
2. DO NOT modify route decorators (@app.get, @router.post, etc.)
3. DO NOT introduce new global variables or 'global' statements
4. ONLY modify the detected function — do not add new functions
5. DO NOT remove business logic — only fix the detected issue
6. DO NOT add imports outside this whitelist: asyncio, logging, typing, contextlib, functools
7. Output MUST be strict JSON — no markdown, no comments, no text outside JSON

OUTPUT SCHEMA (strict):
{
  "explanation": "Why this patch fixes the issue (1-2 sentences)",
  "patch": {
    "type": "replace_function",
    "target": "exact function name",
    "new_code": "complete corrected function definition (including def/async def line)"
  },
  "risk_score_after": <estimated 0-100 risk score after fix>
}
"""

REVIEW_SYSTEM_PROMPT = """\
You are BlastShield Safety Reviewer. You review a code patch that was generated to fix
a production issue.

Analyze the patch for:
1. Race conditions — does the patch introduce shared mutable state access?
2. Blocking calls — does the patch add time.sleep(), requests.get(), or file I/O in async context?
3. Unsafe patterns — eval, exec, subprocess, unsanitized I/O?
4. Logic errors — does the patch preserve the original business logic?
5. Missing error handling — does the patch remove try/except blocks?

OUTPUT SCHEMA (strict JSON):
{
  "safe": true/false,
  "issues": ["list of issues found, empty if safe"],
  "recommendation": "apply" | "regenerate" | "reject"
}
"""


def build_patch_prompt(
    violation: RuleViolation,
    function_source: str,
    file_source: str,
    allowed_imports: list[str] | None = None,
) -> str:
    """
    Build a structured prompt for patch generation.

    Args:
        violation: The rule violation to fix
        function_source: Source code of the affected function
        file_source: Full file source (for context, not modification)
        allowed_imports: Override the import whitelist

    Returns:
        Complete prompt string for LLM
    """
    imports_whitelist = allowed_imports or [
        "asyncio", "logging", "typing", "contextlib", "functools",
    ]

    violation_data = {
        "rule_id": violation.rule_id,
        "severity": violation.severity.value if hasattr(violation.severity, "value") else violation.severity,
        "file": violation.file,
        "line": violation.line,
        "end_line": violation.end_line or violation.line,
        "title": violation.title,
        "description": violation.description,
        "evidence": violation.evidence,
        "affected_function": violation.affected_function,
    }

    prompt = f"""{PATCH_SYSTEM_PROMPT}

=== VIOLATION (detected deterministically — this is a FACT) ===
{json.dumps(violation_data, indent=2)}

=== AFFECTED FUNCTION SOURCE ===
```python
{function_source}
```

=== ALLOWED IMPORT WHITELIST ===
{json.dumps(imports_whitelist)}

Generate a corrected version of ONLY the function above.
Respond with STRICT JSON only. No markdown, no comments, no text outside JSON.
"""
    return prompt


def build_review_prompt(
    violation: RuleViolation,
    original_code: str,
    patched_code: str,
) -> str:
    """
    Build a prompt for LLM self-review of a generated patch.

    Args:
        violation: The original violation
        original_code: Original function code
        patched_code: Generated patch code

    Returns:
        Review prompt string
    """
    prompt = f"""{REVIEW_SYSTEM_PROMPT}

=== ORIGINAL VIOLATION ===
Rule: {violation.rule_id}
Description: {violation.description}

=== ORIGINAL FUNCTION ===
```python
{original_code}
```

=== PROPOSED PATCH ===
```python
{patched_code}
```

Review this patch carefully. Respond with STRICT JSON only.
"""
    return prompt
