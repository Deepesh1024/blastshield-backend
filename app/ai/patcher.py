"""
BlastShield — AI-powered patch generation via Bedrock.

Guarantees a non-empty unified diff when a risk is detected:
  1. Try Bedrock for an AI-generated patch
  2. Fall back to a deterministic static patch
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("blastshield.patcher")

MODEL_ID = "us.amazon.nova-lite-v1:0"


def _static_patch_while_true(risk: dict) -> str:
    """Generate a deterministic safety-counter patch for while True loops."""
    ls = risk["line_start"]
    le = risk["line_end"]
    return (
        f"--- a/file.py\n"
        f"+++ b/file.py\n"
        f"@@ -{ls},{le - ls + 1} +{ls},{le - ls + 3} @@\n"
        f"-while True:\n"
        f"+_safety_counter = 0\n"
        f"+while _safety_counter < 1000:\n"
        f"+    _safety_counter += 1\n"
    )


def _static_patch_infinite_iter(risk: dict) -> str:
    """Generate a deterministic break-after-N patch for infinite iterators."""
    ls = risk["line_start"]
    le = risk["line_end"]
    return (
        f"--- a/file.py\n"
        f"+++ b/file.py\n"
        f"@@ -{ls},{le - ls + 1} +{ls},{le - ls + 3} @@\n"
        f"+_iter_count = 0\n"
        f" # Add safety break after 1000 iterations\n"
        f"+    _iter_count += 1\n"
        f"+    if _iter_count >= 1000:\n"
        f"+        break\n"
    )


def _get_static_patch(risk: dict) -> str:
    """Select the right static fallback patch based on the risk evidence."""
    evidence = risk.get("evidence", "")
    if "while True" in evidence:
        return _static_patch_while_true(risk)
    return _static_patch_infinite_iter(risk)


async def generate_patch(client, risk: dict, code: str) -> str:
    """Ask Bedrock to generate a unified diff patch for the risk.

    GUARANTEES a non-empty patch string when called (falls back to static).
    """
    prompt = (
        "Generate the smallest unified diff patch that fixes this infinite loop risk. "
        "Add a safety counter or break condition. Output ONLY the unified diff, "
        "starting with --- and +++. No explanation, no markdown fences.\n\n"
        f"Evidence: {risk['evidence']}\n"
        f"Lines {risk['line_start']}-{risk['line_end']}\n\n"
        f"Full source:\n```python\n{code}\n```"
    )

    try:
        body = json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 300, "temperature": 0.3},
        })

        response = client.invoke_model(modelId=MODEL_ID, body=body)
        raw = response["body"].read()
        result = json.loads(raw)
        logger.info("Bedrock patch response keys: %s", list(result.keys()))

        # Amazon Nova format: result.output.message.content[0].text
        patch_text = result["output"]["message"]["content"][0]["text"].strip()

        # Strip markdown fences if model wrapped the diff
        if patch_text.startswith("```"):
            lines = patch_text.splitlines()
            lines = [l for l in lines if not l.startswith("```")]
            patch_text = "\n".join(lines).strip()

        # Validate: must look like a diff
        if "---" in patch_text or "@@" in patch_text or patch_text.startswith("diff"):
            return patch_text

        logger.warning("Bedrock patch not valid diff format — using static fallback")

    except Exception:
        logger.warning("Bedrock patch generation failed — using static fallback", exc_info=True)

    # Guaranteed non-empty fallback
    return _get_static_patch(risk)
