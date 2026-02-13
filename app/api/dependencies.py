"""
FastAPI Dependencies — Shared singletons injected via Depends().
"""

from __future__ import annotations

from functools import lru_cache

from app.audit.logger import AuditLogger
from app.cache.file_cache import FileCache
from app.config import settings
from app.llm.gateway import LLMGateway
from app.workers.scan_worker import ScanWorker


@lru_cache
def get_file_cache() -> FileCache:
    """Shared file cache singleton."""
    return FileCache()


@lru_cache
def get_audit_logger() -> AuditLogger:
    """Shared audit logger singleton."""
    return AuditLogger()


@lru_cache
def get_llm_gateway() -> LLMGateway:
    """Shared LLM gateway singleton."""
    return LLMGateway()


@lru_cache
def get_scan_worker() -> ScanWorker:
    """Shared scan worker singleton."""
    return ScanWorker(
        cache=get_file_cache(),
        llm_gateway=get_llm_gateway(),
    )
