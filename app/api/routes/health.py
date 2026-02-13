"""
Health Check Route — GET /health
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": settings.blastshield_model,
        "version": "2.0.0",
        "engine": "deterministic-first",
    }
