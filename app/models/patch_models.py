"""
Patch Data Models — Request/Response schemas for the patch generation engine.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PatchTarget(BaseModel):
    """A single violation target for patch generation."""

    rule_id: str = Field(..., description="Rule ID from the deterministic engine")
    file_path: str = Field(..., description="File containing the violation")
    function_name: str = Field(default="", description="Target function name")
    line_start: int = Field(..., description="Start line of the violation")
    line_end: int = Field(..., description="End line of the violation")
    severity: str = Field(default="high", description="Violation severity")
    failure_class: str = Field(default="", description="Failure classification")
    structural_summary: str = Field(default="", description="Human-readable summary of the issue")


class PatchRequest(BaseModel):
    """Request body for POST /patch endpoint."""

    files: list[PatchFileInput] = Field(..., description="Source files to patch")
    target_rule_ids: list[str] | None = Field(
        default=None,
        description="Optional: only patch these rule IDs. If None, patch all detected.",
    )
    max_retries: int | None = Field(
        default=None,
        description="Override max LLM retries (default from config)",
    )
    use_fallback: bool = Field(
        default=True,
        description="Fall back to deterministic patches if LLM fails",
    )


class PatchFileInput(BaseModel):
    """A source file submitted for patching."""

    path: str = Field(..., description="File path")
    content: str = Field(..., description="File source content")


class PatchResult(BaseModel):
    """Result of patching a single violation."""

    rule_id: str
    target_function: str = ""
    file_path: str = ""
    status: Literal["applied", "rejected", "rollback", "fallback", "failed"] = "failed"
    explanation: str = ""
    original_code: str = Field(default="", description="Original function code")
    patched_code: str = Field(default="", description="New function code")
    validation_errors: list[str] = Field(default_factory=list)
    risk_score_before: int = 0
    risk_score_after: int = 0
    llm_attempts: int = 0
    used_fallback: bool = False


class PatchResponse(BaseModel):
    """Response from POST /patch endpoint."""

    message: str = "patch_complete"
    results: list[PatchResult] = Field(default_factory=list)
    total_violations: int = 0
    patches_applied: int = 0
    patches_rejected: int = 0
    patches_rolled_back: int = 0
    risk_score_before: int = 0
    risk_score_after: int = 0
    patched_sources: dict[str, str] = Field(
        default_factory=dict,
        description="Map of file_path -> patched source content",
    )


# Fix forward reference — PatchRequest references PatchFileInput
PatchRequest.model_rebuild()
