"""
Patch Route — POST /patch

Accepts source files and optional target rule IDs, runs the full patch generation
pipeline, and returns structured results with patched sources.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.dependencies import get_scan_worker
from app.config import settings
from app.engine.pipeline import PatchPipeline
from app.llm.gateway import LLMGateway
from app.models.patch_models import PatchFileInput, PatchRequest, PatchResponse

logger = logging.getLogger("blastshield.api.patch")

router = APIRouter()


def _get_pipeline() -> PatchPipeline:
    """Create a PatchPipeline instance with LLM gateway."""
    try:
        llm = LLMGateway()
    except Exception:
        llm = None
    return PatchPipeline(llm_gateway=llm)


@router.post("/patch", response_model=PatchResponse)
async def generate_patches(request: PatchRequest):
    """
    Generate and validate patches for detected violations.

    Pipeline: detect → generate → validate → apply → re-scan → rollback-if-needed

    Request body:
        - files: list of source files
        - target_rule_ids: optional filter for specific rules
        - max_retries: optional override for LLM retry count
        - use_fallback: whether to use deterministic fallbacks (default: true)

    Response:
        - results: per-violation patch results with status
        - patched_sources: map of file_path → patched source content
        - risk scores before/after
    """
    if not request.files:
        return PatchResponse(
            message="error: no files provided",
            total_violations=0,
        )

    # Filter oversized files
    files = [
        f for f in request.files
        if len(f.content.encode("utf-8")) <= settings.max_file_size_bytes
    ]

    if not files:
        return PatchResponse(
            message="error: all files exceed size limit",
            total_violations=0,
        )

    pipeline = _get_pipeline()

    # Override retries if specified
    if request.max_retries is not None:
        pipeline.max_retries = request.max_retries

    try:
        response = await pipeline.run(
            files=files,
            target_rule_ids=request.target_rule_ids,
            use_fallback=request.use_fallback,
        )
        return response
    except Exception as e:
        logger.exception(f"Patch pipeline failed: {e}")
        return PatchResponse(
            message=f"error: {str(e)}",
            total_violations=0,
        )
