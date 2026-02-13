"""
BlastShield FastAPI Application — Main entry point.

Replaces the legacy Flask backend.py with a production-grade async application.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, pr_scan, scan
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("blastshield")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    logger.info("🛡️  BlastShield v2.0.0 starting")
    logger.info(f"   Model: {settings.blastshield_model}")
    logger.info(f"   LLM threshold: risk > {settings.llm_risk_threshold}")
    logger.info(f"   Test harness: {'enabled' if settings.test_harness_enabled else 'disabled'}")
    logger.info(f"   Cache TTL: {settings.cache_ttl_seconds}s")
    yield
    logger.info("🛡️  BlastShield shutting down")


app = FastAPI(
    title="BlastShield",
    description="Production-grade AI-assisted deployment safety engine",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health.router)
app.include_router(scan.router)
app.include_router(pr_scan.router)
