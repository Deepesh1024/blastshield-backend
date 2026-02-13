"""
Rule Engine Data Models — Violations, results, and rule metadata.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_WEIGHTS: dict[Severity, int] = {
    Severity.CRITICAL: 10,
    Severity.HIGH: 7,
    Severity.MEDIUM: 4,
    Severity.LOW: 1,
}


class RuleViolation(BaseModel):
    """A single deterministic rule violation."""

    rule_id: str = Field(..., description="Unique rule identifier, e.g. 'dangerous_eval'")
    severity: Severity
    file: str = Field(..., description="File path where violation was found")
    line: int = Field(..., description="Line number of violation")
    end_line: int | None = Field(default=None, description="End line of violation range")
    title: str = Field(..., description="Short human-readable violation title")
    description: str = Field(..., description="Detailed deterministic explanation")
    evidence: list[str] = Field(
        default_factory=list,
        description="Deterministic evidence chain (AST paths, variable traces, etc.)",
    )
    affected_function: str = Field(default="", description="Function where violation occurs")
    graph_node_id: str = Field(default="", description="Call graph node ID for blast radius")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Rule-specific extra data"
    )


class RuleResult(BaseModel):
    """Result of running all rules on a set of modules."""

    violations: list[RuleViolation] = Field(default_factory=list)
    rules_executed: list[str] = Field(default_factory=list)
    total_files_scanned: int = 0
    scan_duration_ms: float = 0.0
