"""
BlastShield — AI-powered risk explanation via Bedrock.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("blastshield.explainer")

MODEL_ID = "us.amazon.nova-lite-v1:0"

FALLBACK_EXPLANATION = (
    "Potential infinite loop detected. This can cause CPU exhaustion and "
    "service unavailability in production under sustained load. "
    "In a deployed microservice, this loop will pin one vCPU at 100%, "
    "trigger health-check failures, and eventually cause cascading "
    "timeouts across dependent services. This matters because a single "
    "infinite loop can take down an entire production environment."
)


async def generate_explanation(client, risk: dict, code_snippet: str) -> str:
    """Ask Bedrock to explain a detected risk in simple English.

    Returns a static fallback string if Bedrock is unavailable or errors.
    """
    prompt = (
        "Explain this Python infinite loop risk in 80-120 words for a junior developer. "
        "Clearly describe a realistic production outage scenario (e.g., CPU exhaustion, "
        "service unavailability, scaling failure). Use simple English. "
        "End with one sentence on why this matters in production.\n\n"
        f"Evidence: {risk['evidence']}\n"
        f"Lines {risk['line_start']}-{risk['line_end']}\n\n"
        f"Code:\n```python\n{code_snippet}\n```"
    )

    try:
        body = json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 300, "temperature": 0.5},
        })

        response = client.invoke_model(modelId=MODEL_ID, body=body)
        raw = response["body"].read()
        result = json.loads(raw)
        logger.info("Bedrock explanation response keys: %s", list(result.keys()))

        # Amazon Nova format: result.output.message.content[0].text
        text = result["output"]["message"]["content"][0]["text"].strip()
        return text if text else FALLBACK_EXPLANATION

    except Exception:
        logger.warning("Bedrock explanation failed — using fallback", exc_info=True)
        return FALLBACK_EXPLANATION
