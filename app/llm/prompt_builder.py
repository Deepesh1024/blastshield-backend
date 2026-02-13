"""
Prompt Builder — Builds structured prompts from Layer 1 deterministic output.

The LLM never receives raw source code. It receives:
- Serialized rule violations (JSON)
- Call graph subgraph (JSON)
- Test failure results (JSON)
- Risk scoring breakdown (JSON)
- Whitelist of valid file paths
"""

from __future__ import annotations

import json

from app.models.graph_models import CallGraph
from app.models.llm_models import LLMPromptContext
from app.models.risk_models import RiskBreakdown
from app.models.rule_models import RuleResult


SYSTEM_PROMPT = """\
You are BlastShield AI, an assistant that explains deterministic code analysis findings.

You MUST NOT invent new issues. You ONLY explain and suggest patches for the violations already detected by the deterministic engine.

You receive:
1. A list of rule violations (detected deterministically — these are FACTS)
2. A call graph subgraph showing affected functions and their relationships
3. Test failure results from automated edge-case testing
4. A risk scoring breakdown

Your task:
- For each violation, write a clear natural language explanation
- Suggest minimal, targeted code patches (only for the affected lines)
- Summarize the overall blast impact

STRICT RULES:
- ONLY reference files from the provided file whitelist
- Patches must target ONLY the violation line range (±5 lines max)
- NEVER invent new violations not in the input
- NEVER reference functions/classes not in the subgraph
- Output STRICT JSON matching this schema:

{
  "explanations": [
    {
      "violation_rule_id": "exact rule_id from input",
      "natural_language_explanation": "...",
      "production_risk_summary": "...",
      "patch_suggestions": [
        {
          "file": "exact file path from whitelist",
          "start_line": number,
          "end_line": number,
          "new_code": "replacement code",
          "rationale": "why this patch fixes the issue"
        }
      ]
    }
  ],
  "blast_impact_summary": "overall impact paragraph",
  "overall_recommendation": "ship/hold/rollback recommendation"
}
"""


def build_prompt(
    rule_result: RuleResult,
    call_graph: CallGraph | None = None,
    risk_breakdown: RiskBreakdown | None = None,
    test_failures_json: str = "[]",
    file_paths: list[str] | None = None,
) -> str:
    """
    Build a structured prompt for the LLM from deterministic analysis output.

    Args:
        rule_result: Deterministic rule violations
        call_graph: Call graph (will be filtered to affected subgraph)
        risk_breakdown: Risk scoring breakdown
        test_failures_json: JSON-serialized test failures
        file_paths: Whitelist of valid file paths

    Returns:
        Complete prompt string for LLM
    """
    # Serialize violations
    violations_data = [
        {
            "rule_id": v.rule_id,
            "severity": v.severity.value if hasattr(v.severity, "value") else v.severity,
            "file": v.file,
            "line": v.line,
            "title": v.title,
            "description": v.description,
            "evidence": v.evidence,
            "affected_function": v.affected_function,
        }
        for v in rule_result.violations
    ]

    # Get affected subgraph
    subgraph_data = {}
    if call_graph:
        violation_nodes = {
            v.graph_node_id for v in rule_result.violations if v.graph_node_id
        }
        if violation_nodes:
            subgraph = call_graph.get_affected_subgraph(violation_nodes, hops=1)
            subgraph_data = subgraph.model_dump()
        else:
            subgraph_data = {"nodes": {}, "edges": []}

    # Risk breakdown
    risk_data = risk_breakdown.model_dump() if risk_breakdown else {}

    # Compose prompt
    prompt = f"""{SYSTEM_PROMPT}

=== DETERMINISTIC VIOLATIONS (FACTS — do not invent more) ===
{json.dumps(violations_data, indent=2)}

=== CALL GRAPH SUBGRAPH ===
{json.dumps(subgraph_data, indent=2)}

=== TEST FAILURES ===
{test_failures_json}

=== RISK BREAKDOWN ===
{json.dumps(risk_data, indent=2)}

=== VALID FILE PATHS (whitelist) ===
{json.dumps(file_paths or [])}

Respond with STRICT JSON only. No markdown, no comments, no text outside JSON.
"""
    return prompt
