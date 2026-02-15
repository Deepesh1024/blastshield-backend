"""
Tests for new detection rules — db_conn_per_request, missing_idempotency,
partial_txn_no_rollback, missing_http_timeout.
"""

from app.core.ast_parser import parse_python
from app.core.rule_engine import RuleEngine


# --- Sample code with DB connection per request ---
DB_CONN_CODE = '''
import sqlite3
from flask import Flask

app = Flask(__name__)

@app.get("/users")
def users():
    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    results = cursor.fetchall()
    conn.close()
    return results
'''

# --- Sample code with missing idempotency ---
MISSING_IDEMPOTENCY_CODE = '''
from fastapi import APIRouter

router = APIRouter()

@router.post("/orders")
async def create_order(data: dict):
    cursor.execute("INSERT INTO orders VALUES (?)", (data["item"],))
    session.commit()
    return {"status": "created"}
'''

# --- Sample code with partial transaction ---
PARTIAL_TXN_CODE = '''
import sqlite3

def save_user(name, email):
    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users VALUES (?, ?)", (name, email))
    cursor.execute("INSERT INTO emails VALUES (?)", (email,))
    conn.commit()
    conn.close()
'''

# --- Sample code with missing HTTP timeout ---
MISSING_TIMEOUT_CODE = '''
import requests

def fetch_data():
    response = requests.get("https://api.example.com/data")
    return response.json()

def post_data(payload):
    response = requests.post("https://api.example.com/submit", json=payload)
    return response.status_code
'''

# --- Clean code ---
CLEAN_CODE = '''
import httpx

async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data", timeout=10)
        return response.json()
'''


def test_db_conn_per_request_detected():
    module_ast = parse_python(DB_CONN_CODE, "app.py")
    engine = RuleEngine()
    result = engine.run({"app.py": module_ast})
    db_violations = [v for v in result.violations if v.rule_id == "db_conn_per_request"]
    assert len(db_violations) > 0
    assert db_violations[0].severity.value == "critical"
    assert "sqlite3.connect" in db_violations[0].description


def test_missing_http_timeout_detected():
    module_ast = parse_python(MISSING_TIMEOUT_CODE, "api.py")
    engine = RuleEngine()
    result = engine.run({"api.py": module_ast})
    timeout_violations = [v for v in result.violations if v.rule_id == "missing_http_timeout"]
    assert len(timeout_violations) >= 2  # both get and post
    assert timeout_violations[0].severity.value == "high"


def test_partial_txn_no_rollback_detected():
    module_ast = parse_python(PARTIAL_TXN_CODE, "db.py")
    engine = RuleEngine()
    result = engine.run({"db.py": module_ast})
    txn_violations = [v for v in result.violations if v.rule_id == "partial_txn_no_rollback"]
    assert len(txn_violations) > 0


def test_clean_code_no_new_violations():
    module_ast = parse_python(CLEAN_CODE, "clean.py")
    engine = RuleEngine()
    result = engine.run({"clean.py": module_ast})
    new_rule_violations = [
        v for v in result.violations
        if v.rule_id in (
            "db_conn_per_request", "missing_idempotency",
            "partial_txn_no_rollback", "missing_http_timeout",
        )
    ]
    assert len(new_rule_violations) == 0


def test_all_12_rules_registered():
    engine = RuleEngine()
    result = engine.run({})
    assert len(result.rules_executed) == 12
    assert "db_conn_per_request" in result.rules_executed
    assert "missing_idempotency" in result.rules_executed
    assert "partial_txn_no_rollback" in result.rules_executed
    assert "missing_http_timeout" in result.rules_executed
