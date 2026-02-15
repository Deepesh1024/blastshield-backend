"""
Tests for AST Validator — verify all 7 structural validation checks.
"""

from app.engine.ast_validator import validate_patch_ast


ORIGINAL_SOURCE = '''
import os

@app.get("/users")
def users():
    """Get all users."""
    data = get_data()
    return data
'''


def test_valid_patch_passes():
    patched = '''
import os

@app.get("/users")
def users():
    """Get all users."""
    try:
        data = get_data()
        return data
    except Exception as e:
        return {"error": str(e)}
'''
    verdict = validate_patch_ast(
        original_source=ORIGINAL_SOURCE,
        patched_source=patched,
        target_function="users",
    )
    assert verdict.valid


def test_rejects_syntax_error():
    patched = '''
def users(
    this is not valid python
'''
    verdict = validate_patch_ast(
        original_source=ORIGINAL_SOURCE,
        patched_source=patched,
        target_function="users",
    )
    assert not verdict.valid
    assert any("syntax error" in e.lower() for e in verdict.errors)


def test_rejects_function_rename():
    patched = '''
import os

@app.get("/users")
def get_users():
    """Get all users."""
    data = get_data()
    return data
'''
    verdict = validate_patch_ast(
        original_source=ORIGINAL_SOURCE,
        patched_source=patched,
        target_function="users",
    )
    assert not verdict.valid
    assert any("renamed or removed" in e for e in verdict.errors)


def test_rejects_new_global_statement():
    patched = '''
import os

@app.get("/users")
def users():
    """Get all users."""
    global shared_state
    data = get_data()
    return data
'''
    verdict = validate_patch_ast(
        original_source=ORIGINAL_SOURCE,
        patched_source=patched,
        target_function="users",
    )
    assert not verdict.valid
    assert any("global" in e.lower() for e in verdict.errors)


def test_rejects_forbidden_import():
    patched = '''
import os
import subprocess

@app.get("/users")
def users():
    """Get all users."""
    data = get_data()
    return data
'''
    verdict = validate_patch_ast(
        original_source=ORIGINAL_SOURCE,
        patched_source=patched,
        target_function="users",
    )
    assert not verdict.valid
    assert any("forbidden import" in e.lower() for e in verdict.errors)


def test_rejects_blocking_call_in_async():
    original_async = '''
import asyncio

async def fetch():
    return await some_io()
'''
    patched_async = '''
import asyncio
import time

async def fetch():
    time.sleep(1)
    return await some_io()
'''
    verdict = validate_patch_ast(
        original_source=original_async,
        patched_source=patched_async,
        target_function="fetch",
        is_async=True,
    )
    assert not verdict.valid
    assert any("blocking" in e.lower() for e in verdict.errors)


def test_rejects_return_removal():
    patched = '''
import os

@app.get("/users")
def users():
    """Get all users."""
    data = get_data()
    print(data)
'''
    verdict = validate_patch_ast(
        original_source=ORIGINAL_SOURCE,
        patched_source=patched,
        target_function="users",
    )
    assert not verdict.valid
    assert any("return" in e.lower() for e in verdict.errors)
