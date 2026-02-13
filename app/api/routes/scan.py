"""
Scan Route — POST /scan

Full project scan endpoint. Accepts a list of files, runs the full
deterministic pipeline, optionally invokes LLM, and returns structured results.

For small projects (≤10 files): runs inline and returns immediately.
For larger projects: queues to background and returns scan_id for polling.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends

from app.api.dependencies import get_audit_logger, get_scan_worker
from app.audit.logger import AuditLogger
from app.config import settings
from app.models.scan_models import (
    FileInput,
    ScanRequest,
    ScanResponse,
    ScanStatusResponse,
)
from app.workers.scan_worker import ScanWorker

logger = logging.getLogger("blastshield.api.scan")

router = APIRouter()

# In-memory background scan store
_background_scans: dict[str, ScanResponse | None] = {}
_background_status: dict[str, str] = {}


@router.post("/scan", response_model=ScanResponse)
async def scan(
    request: ScanRequest,
    worker: ScanWorker = Depends(get_scan_worker),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """
    Full project scan.

    - ≤ background_file_threshold files: runs inline, returns full response
    - > threshold: queues to background, returns scan_id for polling
    """
    # Legacy compatibility: accept 'combined' field
    files = request.files
    if not files and request.combined:
        files = [FileInput(path="unknown", content=request.combined)]

    if not files:
        return ScanResponse(
            message="error",
            report=None,
        )

    # Filter oversized files
    files = [
        f for f in files
        if len(f.content.encode("utf-8")) <= settings.max_file_size_bytes
    ]

    if len(files) > settings.background_file_threshold:
        # Queue to background
        scan_id = f"bg-{id(files) % 100000:05d}"
        _background_scans[scan_id] = None
        _background_status[scan_id] = "running"

        async def _run_background():
            try:
                result = await worker.run_scan(files, scan_mode="full")
                result.scan_id = scan_id
                _background_scans[scan_id] = result
                _background_status[scan_id] = "complete"
                if result.report and result.report.audit:
                    audit.log(result.report.audit)
            except Exception as e:
                logger.error(f"Background scan {scan_id} failed: {e}")
                _background_status[scan_id] = "failed"

        asyncio.create_task(_run_background())

        return ScanResponse(
            message="scan_queued",
            scan_id=scan_id,
        )

    # Inline scan
    response = await worker.run_scan(files, scan_mode="full")

    # Audit log
    if response.report and response.report.audit:
        audit.log(response.report.audit)

    return response


@router.get("/scan/{scan_id}/status", response_model=ScanStatusResponse)
async def scan_status(scan_id: str):
    """Poll the status of a background scan."""
    status = _background_status.get(scan_id, "not_found")

    if status == "not_found":
        return ScanStatusResponse(
            scan_id=scan_id,
            status="failed",
            error="Scan not found",
        )

    result = _background_scans.get(scan_id)
    return ScanStatusResponse(
        scan_id=scan_id,
        status=status,
        progress=1.0 if status == "complete" else 0.5,
        report=result.report if result else None,
    )
