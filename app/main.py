"""
BlastShield FastAPI Application — Minimal hackathon prototype.

Single-endpoint Python code scanner:
  POST /scan   → detect infinite loops, score risk, AI explanation + patch
  GET  /health → {"status": "ok"}
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.scan import router as scan_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("blastshield")

app = FastAPI(
    title="BlastShield",
    description="AI-powered Python code scanner — infinite loop detection",
    version="1.0.0",
)

# CORS — permissive for hackathon demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register scan route
app.include_router(scan_router)

from fastapi.exceptions import RequestValidationError
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    logger.error(f"Validation Error. Raw body: {body.decode('utf-8')[:500]} | Errors: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body.decode("utf-8")[:100]},
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
