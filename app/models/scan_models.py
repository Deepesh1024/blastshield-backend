"""
Scan Request/Response Models — API contract schemas.

These are the public-facing Pydantic models used by FastAPI endpoints.
The response schema is a backward-compatible superset of the legacy Flask API.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.risk_models import RiskBreakdown


class FileInput(BaseModel):
    """A single file submitted for scanning."""

    path: str = Field(..., description="File path (absolute or relative)")
    content: str = Field(..., description="File source content")


class ScanRequest(BaseModel):
    """Request body for /scan and /pr-scan endpoints."""

    files: list[FileInput] = Field(default_factory=list)
    scan_mode: Literal["full", "pr"] = "full"
    # Legacy compatibility: accept 'combined' field
    combined: str | None = Field(
        default=None, description="Legacy: single combined code string"
    )


class Patch(BaseModel):
    """A code patch suggestion targeting a specific line range."""

    file: str
    start_line: int
    end_line: int
    new_code: str


class Issue(BaseModel):
    """A single issue found during scanning."""

    id: str
    severity: Literal["critical", "high", "medium", "low"]
    file: str
    line: int = 0
    rule_id: str = Field(default="", description="Deterministic rule that detected this")
    issue: str = Field(..., description="Short issue title")
    explanation: str = Field(..., description="Detailed explanation")
    risk: str = Field(default="", description="Production risk description")
    evidence: list[str] = Field(
        default_factory=list, description="Deterministic evidence chain"
    )
    patches: list[Patch] = Field(default_factory=list)
    testImpact: list[str] = Field(default_factory=list)  # noqa: N815 — legacy compat


class AuditEntry(BaseModel):
    """Audit metadata for a scan."""

    scan_id: str
    files_scanned: int
    violations_found: int
    risk_score: int
    llm_invoked: bool
    llm_tokens_used: int = 0
    duration_ms: float = 0.0
    deterministic_only: bool = True


class ScanReport(BaseModel):
    """Full scan report."""

    issues: list[Issue] = Field(default_factory=list)
    riskScore: int = Field(default=0, ge=0, le=100)  # noqa: N815 — legacy compat
    risk_breakdown: RiskBreakdown | None = None
    summary: str = ""
    llm_used: bool = False
    deterministic_only: bool = True
    audit: AuditEntry | None = None


class ScanResponse(BaseModel):
    """Top-level response for scan endpoints."""

    message: str = "scan_complete"
    scan_id: str = ""
    report: ScanReport | None = None


class ScanStatusResponse(BaseModel):
    """Response for polling a background scan."""

    scan_id: str
    status: Literal["queued", "running", "complete", "failed"]
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    report: ScanReport | None = None
    error: str | None = None
