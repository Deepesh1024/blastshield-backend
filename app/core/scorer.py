"""
BlastShield — Risk score calculator.
"""

from __future__ import annotations


def calculate_score(risks: list[dict]) -> int:
    """Compute a 0-100 risk score from detected risks.

    0   → no risks found
    50  → one risk
    100 → two or more risks
    """
    if not risks:
        return 0
    return min(100, 50 * len(risks))
