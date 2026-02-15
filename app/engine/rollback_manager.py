"""
Rollback Manager — Stores original source snapshots for rollback capability.

Before any patch is applied, the original source is saved.
If the patch fails validation or re-scan, the original is restored.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("blastshield.engine.rollback")


@dataclass
class Snapshot:
    """A source code snapshot for rollback."""

    file_path: str
    function_name: str
    original_source: str


class RollbackManager:
    """
    Manages source code snapshots for safe rollback.

    Usage:
        mgr = RollbackManager()
        mgr.save_snapshot("app.py", "users", original_source)
        # ... apply patch ...
        if patch_failed:
            original = mgr.rollback("app.py", "users")
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, Snapshot] = {}

    def _key(self, file_path: str, function_name: str) -> str:
        return f"{file_path}::{function_name}"

    def save_snapshot(
        self, file_path: str, function_name: str, source: str
    ) -> None:
        """Save a snapshot of the original source before patching."""
        key = self._key(file_path, function_name)
        self._snapshots[key] = Snapshot(
            file_path=file_path,
            function_name=function_name,
            original_source=source,
        )
        logger.debug(f"Snapshot saved: {key}")

    def rollback(self, file_path: str, function_name: str) -> str | None:
        """
        Retrieve the original source for rollback.

        Returns:
            Original source string, or None if no snapshot exists.
        """
        key = self._key(file_path, function_name)
        snapshot = self._snapshots.get(key)
        if snapshot is None:
            logger.error(f"No snapshot found for rollback: {key}")
            return None
        logger.info(f"Rolling back: {key}")
        return snapshot.original_source

    def get_original(self, file_path: str, function_name: str) -> str | None:
        """Get the original source without removing the snapshot."""
        key = self._key(file_path, function_name)
        snapshot = self._snapshots.get(key)
        return snapshot.original_source if snapshot else None

    def has_snapshot(self, file_path: str, function_name: str) -> bool:
        """Check if a snapshot exists."""
        return self._key(file_path, function_name) in self._snapshots

    def clear(self) -> None:
        """Clear all snapshots."""
        self._snapshots.clear()
        logger.debug("All snapshots cleared")
