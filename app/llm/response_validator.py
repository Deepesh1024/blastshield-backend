"""
Response Validator — Strict JSON schema validation for LLM output.

Rejects responses that:
- Reference files not in the input whitelist
- Propose patches outside violation line ranges
- Fail JSON parsing
- Contain hallucinated rule IDs not in the deterministic output
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from app.models.llm_models import LLMResponse

logger = logging.getLogger("blastshield.llm.validator")


class ValidationResult:
    """Result of response validation."""

    def __init__(self) -> None:
        self.valid = True
        self.errors: list[str] = []
        self.response: LLMResponse | None = None

    def add_error(self, error: str) -> None:
        self.valid = False
        self.errors.append(error)


def validate_llm_response(
    parsed: dict[str, Any] | None,
    valid_file_paths: set[str],
    valid_rule_ids: set[str],
    violation_line_ranges: dict[str, tuple[int, int]],  # rule_id -> (start, end)
    line_tolerance: int = 5,
) -> ValidationResult:
    """
    Validate an LLM response against strict constraints.

    Args:
        parsed: Parsed JSON dict from LLM
        valid_file_paths: Set of file paths that were in the scan input
        valid_rule_ids: Set of rule_ids from deterministic violations
        violation_line_ranges: Map of rule_id -> (line, end_line) for range checking
        line_tolerance: Max lines beyond violation range for patches (default ±5)

    Returns:
        ValidationResult with .valid, .errors, and .response
    """
    result = ValidationResult()

    if parsed is None:
        result.add_error("LLM returned non-JSON or empty response")
        return result

    # Schema validation via Pydantic
    try:
        response = LLMResponse(**parsed)
    except ValidationError as e:
        result.add_error(f"Schema validation failed: {e}")
        return result

    result.response = response

    # Validate each explanation
    for explanation in response.explanations:
        # Check rule_id exists in deterministic output
        if explanation.violation_rule_id not in valid_rule_ids:
            result.add_error(
                f"Hallucinated rule_id: '{explanation.violation_rule_id}' "
                f"not in deterministic output {valid_rule_ids}"
            )

        # Validate patch suggestions
        for patch in explanation.patch_suggestions:
            # Check file is in whitelist
            if patch.file not in valid_file_paths:
                result.add_error(
                    f"Patch references file '{patch.file}' not in scan input. "
                    f"Valid files: {valid_file_paths}"
                )

            # Check patch line range is near the violation
            if explanation.violation_rule_id in violation_line_ranges:
                viol_start, viol_end = violation_line_ranges[
                    explanation.violation_rule_id
                ]
                if (
                    patch.start_line < viol_start - line_tolerance
                    or patch.end_line > viol_end + line_tolerance
                ):
                    result.add_error(
                        f"Patch line range {patch.start_line}-{patch.end_line} "
                        f"is outside tolerance of violation range "
                        f"{viol_start}-{viol_end} (±{line_tolerance})"
                    )

    if result.errors:
        logger.warning(
            f"LLM response validation failed with {len(result.errors)} errors: "
            f"{result.errors}"
        )

    return result
