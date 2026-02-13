"""
Audit Logger — Structured JSON-lines audit trail.

Records every scan with: timestamp, scan_id, files scanned, violations found,
risk score, LLM invocation details, and duration.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from app.config import settings
from app.models.scan_models import AuditEntry

logger = logging.getLogger("blastshield.audit")


class AuditLogger:
    """Writes structured audit entries to a JSON-lines file."""

    def __init__(self, log_path: str | None = None) -> None:
        self.log_path = Path(log_path or settings.audit_log_path)

    def log(self, entry: AuditEntry) -> None:
        """Append an audit entry to the log file."""
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **entry.model_dump(),
        }

        try:
            with open(self.log_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            logger.error(f"Failed to write audit log: {e}")

    def read_recent(self, count: int = 50) -> list[dict]:
        """Read the most recent N audit entries."""
        if not self.log_path.exists():
            return []

        entries: list[dict] = []
        try:
            with open(self.log_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            return []

        return entries[-count:]
