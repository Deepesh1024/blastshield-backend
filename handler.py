"""
AWS Lambda handler — Mangum wrapper for FastAPI.
"""

from mangum import Mangum

from app.main import app

handler = Mangum(app, lifespan="off")
