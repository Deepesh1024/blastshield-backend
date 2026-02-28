"""
BlastShield — POST /scan endpoint.

Accepts {"code": str}, parses with tree-sitter, detects infinite loops,
scores the risk, and enriches with Bedrock AI explanation + patch.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ai.bedrock import get_bedrock_client
from app.ai.explainer import FALLBACK_EXPLANATION, generate_explanation
from app.ai.patcher import generate_patch
from app.core.parser import PythonParser
from app.core.rules.infinite_loop import detect_infinite_loops
from app.core.scorer import calculate_score

logger = logging.getLogger("blastshield.scan")
router = APIRouter()

# Max input size: 50 KB
MAX_CODE_LENGTH = 50_000

# Shared singleton — created once per Lambda cold start
_parser = PythonParser()


class ScanRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Python source code to scan")


class ScanResponse(BaseModel):
    risk_score: int
    risks: list[dict]
    explanation: str
    suggested_patch: str


_SAFE_FALLBACK = ScanResponse(
    risk_score=0,
    risks=[],
    explanation="Scan failed safely.",
    suggested_patch="",
)


@router.post("/scan", response_model=ScanResponse)
async def scan_code(req: ScanRequest):
    """Scan Python code for infinite loop risks."""
    try:
        # Input size guard
        if len(req.code) > MAX_CODE_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Code exceeds maximum length of {MAX_CODE_LENGTH} characters",
            )

        # Parse
        try:
            tree, source_bytes = _parser.parse(req.code)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="Could not parse the provided Python code",
            )

        # Detect
        risks = detect_infinite_loops(tree, source_bytes)
        risk_score = calculate_score(risks)

        # No risks → clean result
        if not risks:
            return ScanResponse(
                risk_score=0,
                risks=[],
                explanation="No infinite loop risks detected. Code looks safe.",
                suggested_patch="",
            )

        # Enrich with Bedrock AI
        try:
            client = get_bedrock_client()
            lines = req.code.splitlines()
            first = risks[0]
            snippet_lines = lines[first["line_start"] - 1 : first["line_end"]]
            snippet = "\n".join(snippet_lines)

            explanation, patch = await asyncio.gather(
                generate_explanation(client, first, snippet),
                generate_patch(client, first, req.code),
            )
        except Exception:
            logger.warning("Bedrock unavailable — using fallback", exc_info=True)
            explanation = FALLBACK_EXPLANATION
            # Still guarantee a non-empty patch via static fallback
            from app.ai.patcher import _get_static_patch
            patch = _get_static_patch(first)

        return ScanResponse(
            risk_score=risk_score,
            risks=risks,
            explanation=explanation,
            suggested_patch=patch,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected scan error")
        return _SAFE_FALLBACK
