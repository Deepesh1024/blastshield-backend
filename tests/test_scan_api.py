"""
Tests for FastAPI Scan API — integration tests for the full pipeline.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "model" in data
    assert data["version"] == "2.0.0"


def test_scan_empty_files():
    response = client.post("/scan", json={"files": []})
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "error"


def test_scan_clean_code(clean_python_code):
    response = client.post("/scan", json={
        "files": [{"path": "clean.py", "content": clean_python_code}]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "scan_complete"
    assert "report" in data
    report = data["report"]
    assert "issues" in report
    assert "riskScore" in report
    assert report["deterministic_only"] is True


def test_scan_vulnerable_code(sample_python_code):
    response = client.post("/scan", json={
        "files": [{"path": "vuln.py", "content": sample_python_code}]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "scan_complete"
    report = data["report"]
    assert len(report["issues"]) > 0
    assert report["riskScore"] > 0

    # Verify issue structure
    issue = report["issues"][0]
    assert "id" in issue
    assert "severity" in issue
    assert "file" in issue
    assert "rule_id" in issue
    assert "explanation" in issue
    assert "evidence" in issue


def test_scan_returns_risk_breakdown(sample_python_code):
    response = client.post("/scan", json={
        "files": [{"path": "vuln.py", "content": sample_python_code}]
    })
    data = response.json()
    report = data["report"]
    assert report["risk_breakdown"] is not None
    breakdown = report["risk_breakdown"]
    assert "total_score" in breakdown
    assert "violation_contributions" in breakdown
    assert "formula" in breakdown


def test_scan_returns_audit(sample_python_code):
    response = client.post("/scan", json={
        "files": [{"path": "vuln.py", "content": sample_python_code}]
    })
    data = response.json()
    report = data["report"]
    assert report["audit"] is not None
    audit = report["audit"]
    assert audit["files_scanned"] == 1
    assert audit["violations_found"] > 0
    assert isinstance(audit["deterministic_only"], bool)


def test_pr_scan(sample_python_code):
    response = client.post("/pr-scan", json={
        "files": [{"path": "changed.py", "content": sample_python_code}]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "scan_complete"
    assert data["report"]["summary"] != ""


def test_legacy_combined_field():
    """Test backward compatibility with legacy 'combined' field."""
    response = client.post("/scan", json={
        "combined": "x = eval(input())"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "scan_complete"
