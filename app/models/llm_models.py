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
