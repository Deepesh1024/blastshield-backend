"""
Test fixtures shared across all BlastShield tests.
"""

import pytest


@pytest.fixture
def sample_python_code():
    """Sample Python code with known vulnerabilities for testing."""
    return '''
import os
import time
import requests

shared_data = []
config_cache = {}

def process_file(user_path):
    """Vulnerable: unsanitized file path."""
    with open(user_path) as f:
        return f.read()

def execute_code(code_string):
    """Vulnerable: dangerous eval."""
    result = eval(code_string)
    return result

async def fetch_data():
    """Vulnerable: blocking I/O in async."""
    response = requests.get("https://api.example.com/data")
    time.sleep(1)
    return response.json()

async def update_shared(item):
    """Vulnerable: mutates shared state."""
    global shared_data
    shared_data.append(item)

async def sync_shared():
    """Vulnerable: also mutates shared state (race condition)."""
    global shared_data
    shared_data.clear()

def retry_api():
    """Vulnerable: retry without backoff."""
    for i in range(10):
        try:
            return requests.get("https://api.example.com")
        except Exception:
            pass

def handler_no_try(data):
    """Vulnerable: missing exception boundary (if decorated as route)."""
    return data["key"]
'''


@pytest.fixture
def clean_python_code():
    """Clean Python code with no violations."""
    return '''
def add(a: int, b: int) -> int:
    """Simple pure function."""
    return a + b

def greet(name: str) -> str:
    """Safe string operation."""
    return f"Hello, {name}"
'''


@pytest.fixture
def sample_files(sample_python_code):
    """Sample file inputs for API testing."""
    from app.models.scan_models import FileInput
    return [FileInput(path="test_app.py", content=sample_python_code)]
