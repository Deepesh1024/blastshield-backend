"""
File Cache — SHA-256 hash-based incremental caching.

Caches AST parse results and rule violations per-file, keyed by content hash.
Unchanged files skip re-parsing entirely.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.models.ast_models import ModuleAST
from app.models.rule_models import RuleViolation


@dataclass
class CacheEntry:
    """A cached analysis result for a single file."""

    content_hash: str
    module_ast: ModuleAST
    violations: list[RuleViolation]
    timestamp: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > settings.cache_ttl_seconds


class FileCache:
    """
    In-memory file-level cache keyed by SHA-256 of file content.

    Upgradeable to Redis/SQLite by swapping the storage backend.
    """

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}

    @staticmethod
    def hash_content(content: str) -> str:
        """Compute SHA-256 hash of file content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get(self, file_path: str, content: str) -> CacheEntry | None:
        """
        Look up cached result for a file.

        Returns None if not cached, expired, or content has changed.
        """
        content_hash = self.hash_content(content)
        key = f"{file_path}:{content_hash}"
        entry = self._store.get(key)

        if entry is None:
            return None

        if entry.is_expired:
            del self._store[key]
            return None

        return entry

    def put(
        self,
        file_path: str,
        content: str,
        module_ast: ModuleAST,
        violations: list[RuleViolation],
    ) -> None:
        """Cache analysis results for a file."""
        content_hash = self.hash_content(content)
        key = f"{file_path}:{content_hash}"
        self._store[key] = CacheEntry(
            content_hash=content_hash,
            module_ast=module_ast,
            violations=violations,
        )

    def invalidate(self, file_path: str) -> int:
        """Remove all cached entries for a file path. Returns count removed."""
        keys_to_remove = [k for k in self._store if k.startswith(f"{file_path}:")]
        for key in keys_to_remove:
            del self._store[key]
        return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()

    @property
    def size(self) -> int:
        """Number of cached entries."""
        return len(self._store)

    def stats(self) -> dict[str, Any]:
        """Cache statistics."""
        expired = sum(1 for e in self._store.values() if e.is_expired)
        return {
            "total_entries": len(self._store),
            "expired_entries": expired,
            "active_entries": len(self._store) - expired,
        }
