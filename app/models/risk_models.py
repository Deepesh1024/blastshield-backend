"""
Risk Scoring Data Models — Breakdown structure for explainable risk scores.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ViolationContribution(BaseModel):
    """How a single violation contributes to the total risk score."""

    rule_id: str
    severity: str
    file: str
    line: int
    base_weight: int
    blast_radius_factor: float
    state_mutation_factor: float
    test_failure_factor: float
    async_boundary_factor: float
    total_factor: float
    weighted_score: float


class RiskBreakdown(BaseModel):
    """Full explainable breakdown of the risk score."""

    total_score: int = Field(
        ..., ge=0, le=100, description="Final risk score 0-100"
    )
    max_possible_score: float = Field(
        default=0.0, description="Maximum possible score given violations"
    )
    violation_contributions: list[ViolationContribution] = Field(
        default_factory=list
    )
    formula: str = Field(
        default="risk = Σ(base_weight × factors) / max_possible × 100",
        description="Human-readable formula used",
    )
    summary: str = Field(default="", description="Human-readable risk summary")
