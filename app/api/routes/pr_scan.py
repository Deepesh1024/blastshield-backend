"""
PR Scan Route — POST /pr-scan

Scans only files changed in a Pull Request.
Returns PR-specific summary for GitHub Actions / PR comments.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.dependencies import get_audit_logger, get_scan_worker
from app.audit.logger import AuditLogger
from app.models.scan_models import FileInput, ScanRequest, ScanResponse
from app.workers.scan_worker import ScanWorker

logger = logging.getLogger("blastshield.api.pr_scan")

router = APIRouter()


@router.post("/pr-scan", response_model=ScanResponse)
async def pr_scan(
    request: ScanRequest,
    worker: ScanWorker = Depends(get_scan_worker),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """
    PR diff-based scan.

    Only analyzes the changed files provided.
    Returns a PR-specific summary suitable for GitHub PR comments.
    """
    files = request.files

    if not files:
        return ScanResponse(
            message="error",
            report=None,
        )

    # PR scans always run inline (typically few files changed)
    response = await worker.run_scan(files, scan_mode="pr")

    # Add PR summary to response
    if response.report:
        if not response.report.summary:
            if response.report.issues:
                critical = sum(1 for i in response.report.issues if i.severity == "critical")
                high = sum(1 for i in response.report.issues if i.severity == "high")
                response.report.summary = (
                    f"BlastShield found {len(response.report.issues)} issues "
                    f"({critical} critical, {high} high) in this PR. "
                    f"Risk score: {response.report.riskScore}/100."
                )
            else:
                response.report.summary = (
                    "BlastShield scan complete. No issues detected in changed files."
                )

    # Audit log
    if response.report and response.report.audit:
        audit.log(response.report.audit)

    return response
