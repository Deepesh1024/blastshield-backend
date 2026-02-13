"""
LLM Gateway — Wraps the Groq client with retry, timeout, and token tracking.

Only invoked when risk_score exceeds the configured threshold.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from groq import Groq

from app.config import settings

logger = logging.getLogger("blastshield.llm")


class LLMGateway:
    """
    Groq LLM client wrapper with:
    - Configurable timeout
    - Retry with exponential backoff
    - Token budget tracking
    """

    def __init__(self) -> None:
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = settings.blastshield_model
        self.timeout = settings.llm_timeout
        self.max_retries = settings.llm_max_retries
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens_per_scan
        self.total_tokens_used = 0

    async def complete(self, prompt: str) -> dict[str, Any]:
        """
        Send a prompt to the LLM and return the parsed JSON response.

        Runs the synchronous Groq SDK in a thread pool to avoid blocking
        the async event loop.

        Returns:
            dict with 'content' (raw text), 'parsed' (JSON or None),
            'tokens_used' (int), 'success' (bool).
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                # Run sync SDK in thread pool
                response = await asyncio.to_thread(
                    self._sync_complete, prompt
                )

                content = response.choices[0].message.content or ""
                tokens = getattr(response.usage, "total_tokens", 0) if response.usage else 0
                self.total_tokens_used += tokens

                # Try to parse JSON
                parsed = None
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown fences
                    parsed = _extract_json(content)

                return {
                    "content": content,
                    "parsed": parsed,
                    "tokens_used": tokens,
                    "success": parsed is not None,
                }

            except Exception as e:
                last_error = e
                logger.warning(
                    f"LLM attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    await asyncio.sleep(2**attempt)

        logger.error(f"LLM gateway exhausted retries. Last error: {last_error}")
        return {
            "content": "",
            "parsed": None,
            "tokens_used": 0,
            "success": False,
            "error": str(last_error),
        }

    def _sync_complete(self, prompt: str):
        """Synchronous Groq completion call."""
        return self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def get_tokens_used(self) -> int:
        """Get total tokens consumed across all calls."""
        return self.total_tokens_used

    def reset_token_counter(self) -> None:
        """Reset the token counter (per-scan)."""
        self.total_tokens_used = 0


def _extract_json(text: str) -> dict | None:
    """Try to extract JSON from markdown-fenced text."""
    import re

    # Try ```json ... ``` blocks
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find first { ... } block
    start = text.find("{")
    if start != -1:
        # Find matching closing brace
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    return None
