"""
BlastShield — AWS Bedrock client factory.

Supports two auth modes:
  1. Bearer token (AWS_BEARER_TOKEN_BEDROCK env var) — direct HTTPS calls
  2. Standard boto3 IAM credentials — SigV4 signing
"""

from __future__ import annotations

import io
import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger("blastshield.bedrock")


class BedrockBearerClient:
    """Minimal Bedrock Runtime client using bearer token auth.

    Mimics the boto3 invoke_model interface so explainer/patcher work unchanged.
    """

    def __init__(self, token: str, region: str = "us-east-1") -> None:
        self._token = token
        self._endpoint = f"https://bedrock-runtime.{region}.amazonaws.com"

    def invoke_model(self, *, modelId: str, body: str | bytes) -> dict:
        """Call Bedrock InvokeModel via HTTPS with bearer token."""
        encoded_model = urllib.parse.quote(modelId, safe="")
        url = f"{self._endpoint}/model/{encoded_model}/invoke"
        if isinstance(body, str):
            body = body.encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        logger.info("Invoking Bedrock model %s via bearer token", modelId)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            return {"body": io.BytesIO(data)}


def get_bedrock_client():
    """Create a Bedrock Runtime client.

    Uses bearer token if AWS_BEARER_TOKEN_BEDROCK is set,
    otherwise falls back to standard boto3 credential chain.
    """
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "").strip()

    if token:
        logger.info("Using Bedrock bearer token auth (region=%s)", region)
        return BedrockBearerClient(token, region)

    # Fallback to boto3 SigV4
    import boto3
    logger.info("Using boto3 IAM auth for Bedrock (region=%s)", region)
    return boto3.client("bedrock-runtime", region_name=region)
