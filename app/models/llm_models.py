"""
LLM Data Models — Schemas for LLM input/output validation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMPatchSuggestion(BaseModel):
    """A patch suggestion from the LLM."""

    file: str
    start_line: int
    end_line: int
    new_code: str
    rationale: str = ""


class LLMExplanation(BaseModel):
    """LLM-generated explanation for a single violation."""

    violation_rule_id: str
    natural_language_explanation: str
    production_risk_summary: str
    patch_suggestions: list[LLMPatchSuggestion] = Field(default_factory=list)


class LLMResponse(BaseModel):
    """Validated LLM response — strict schema enforcement."""

    explanations: list[LLMExplanation] = Field(default_factory=list)
    blast_impact_summary: str = ""
    overall_recommendation: str = ""


class LLMPromptContext(BaseModel):
    """Structured context sent to the LLM (not raw code)."""

    violations_json: str = Field(
        ..., description="JSON-serialized list of RuleViolation objects"
    )
    subgraph_json: str = Field(
        ..., description="JSON-serialized call graph subgraph around violations"
    )
    test_failures_json: str = Field(
        default="[]", description="JSON-serialized test failure results"
    )
    risk_breakdown_json: str = Field(
        ..., description="JSON-serialized RiskBreakdown"
    )
    file_paths: list[str] = Field(
        default_factory=list, description="Whitelist of valid file paths"
    )


class LLMPatchOutput(BaseModel):
    """Strict JSON output schema for LLM patch generation."""

    type: str = Field(
        default="replace_function",
        description="Patch type: 'replace_function'",
    )
    target: str = Field(..., description="Target function name")
    new_code: str = Field(..., description="Replacement function code")


class LLMPatchGeneration(BaseModel):
    """Full LLM patch generation response — strict schema."""

    explanation: str = Field(..., description="Why this patch fixes the issue")
    patch: LLMPatchOutput = Field(..., description="The patch to apply")
    risk_score_after: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Estimated risk score after applying patch",
    )


class LLMReviewVerdict(BaseModel):
    """LLM's verdict when reviewing its own patch."""

    safe: bool = Field(..., description="Whether the patch is safe to apply")
    issues: list[str] = Field(
        default_factory=list,
        description="Issues found in the patch",
    )
    recommendation: str = Field(
        default="apply",
        description="'apply', 'regenerate', or 'reject'",
    )
