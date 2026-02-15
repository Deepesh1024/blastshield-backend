"""
Tests for Patch Pipeline — integration tests for the full pipeline.

Tests patch applier, rollback manager, and re-scan.
"""

import pytest
from app.engine.patch_applier import apply_function_patch, apply_line_range_patch
from app.engine.rollback_manager import RollbackManager
from app.engine.rescan import rescan_patched_source
from app.engine.fallback_patches import generate_fallback_patch


# --- Patch Applier Tests ---

SAMPLE_SOURCE = '''import os

def process(data):
    """Process the data."""
    result = data * 2
    return result

def other():
    return 42
'''


def test_apply_function_patch():
    new_func = '''def process(data):
    """Process the data safely."""
    try:
        result = data * 2
        return result
    except Exception:
        return None
'''
    patched = apply_function_patch(SAMPLE_SOURCE, "process", new_func)
    assert patched is not None
    assert "try:" in patched
    assert "def other():" in patched  # Other function preserved
    assert "def process(data):" in patched


def test_apply_function_patch_missing_function():
    result = apply_function_patch(SAMPLE_SOURCE, "nonexistent", "def nonexistent(): pass")
    assert result is None


def test_apply_function_patch_bad_syntax():
    result = apply_function_patch(SAMPLE_SOURCE, "process", "def process(:\n    invalid")
    assert result is None


def test_apply_line_range_patch():
    patched = apply_line_range_patch(SAMPLE_SOURCE, 5, 5, "    result = data * 3")
    assert patched is not None
    assert "data * 3" in patched


# --- Rollback Manager Tests ---

def test_rollback_manager_save_and_restore():
    mgr = RollbackManager()
    mgr.save_snapshot("app.py", "users", "original code")
    assert mgr.has_snapshot("app.py", "users")
    restored = mgr.rollback("app.py", "users")
    assert restored == "original code"


def test_rollback_manager_no_snapshot():
    mgr = RollbackManager()
    result = mgr.rollback("app.py", "nonexistent")
    assert result is None


def test_rollback_manager_clear():
    mgr = RollbackManager()
    mgr.save_snapshot("a.py", "foo", "code1")
    mgr.save_snapshot("b.py", "bar", "code2")
    mgr.clear()
    assert not mgr.has_snapshot("a.py", "foo")
    assert not mgr.has_snapshot("b.py", "bar")


# --- Re-Scan Tests ---

SAFE_SOURCE = '''
def add(a: int, b: int) -> int:
    return a + b
'''

UNSAFE_SOURCE = '''
import requests

def fetch():
    return requests.get("https://example.com")
'''


def test_rescan_clean_code_passes():
    result = rescan_patched_source(
        patched_source=SAFE_SOURCE,
        file_path="clean.py",
        target_rule_id="missing_http_timeout",
        original_risk_score=50,
    )
    assert result.target_rule_eliminated
    assert result.risk_score_after <= 50


def test_rescan_detects_remaining_violations():
    result = rescan_patched_source(
        patched_source=UNSAFE_SOURCE,
        file_path="api.py",
        target_rule_id="missing_http_timeout",
        original_risk_score=50,
    )
    assert not result.target_rule_eliminated


# --- Fallback Patches Tests ---

def test_fallback_missing_http_timeout():
    source = '''def fetch():
    response = requests.get("https://example.com")
    return response.json()
'''
    patched = generate_fallback_patch("missing_http_timeout", source, "fetch")
    assert patched is not None
    assert "timeout" in patched


def test_fallback_blocking_io():
    source = '''async def fetch():
    time.sleep(1)
    response = requests.get("https://example.com")
    return response
'''
    patched = generate_fallback_patch("blocking_io_in_async", source, "fetch")
    assert patched is not None
    assert "asyncio.sleep" in patched


def test_fallback_unknown_rule():
    result = generate_fallback_patch("unknown_rule_xyz", "def foo(): pass", "foo")
    assert result is None
