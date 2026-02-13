"""
Scan Worker — Async orchestrator running the full analysis pipeline.

Pipeline:
1. Parse AST for each file (with caching)
2. Build call graph
3. Run data flow analysis
4. Execute rule engine (8 deterministic rules)
5. Optionally generate + run edge-case tests
6. Compute risk score
7. If risk > threshold → invoke LLM for explanations
8. Validate LLM response or fall back to deterministic
9. Assemble final ScanResponse
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from app.cache.file_cache import FileCache
from app.config import settings
from app.core.ast_parser import parse_file
from app.core.call_graph import build_call_graph
from app.core.data_flow import analyze_data_flow
from app.core.risk_scorer import compute_risk_score
from app.core.rule_engine import RuleEngine
from app.core.test_harness import generate_edge_cases, run_tests
from app.llm.fallback import generate_fallback_issues
from app.llm.gateway import LLMGateway
from app.llm.prompt_builder import build_prompt
from app.llm.response_validator import validate_llm_response
from app.models.ast_models import ModuleAST
from app.models.scan_models import (
    AuditEntry,
    FileInput,
    Issue,
    Patch,
    ScanReport,
    ScanResponse,
)

logger = logging.getLogger("blastshield.worker")


class ScanWorker:
    """Async scan orchestrator implementing the full analysis pipeline."""

    def __init__(
        self,
        cache: FileCache | None = None,
        llm_gateway: LLMGateway | None = None,
    ) -> None:
        self.cache = cache or FileCache()
        self.llm_gateway = llm_gateway
        self.rule_engine = RuleEngine()

        # In-memory scan store (upgrade to Redis for production)
        self._scans: dict[str, ScanResponse] = {}
        self._scan_status: dict[str, str] = {}  # scan_id -> status
        self._scan_progress: dict[str, float] = {}

    async def run_scan(
        self,
        files: list[FileInput],
        scan_mode: str = "full",
    ) -> ScanResponse:
        """
        Execute the full analysis pipeline.

        Args:
            files: List of files to scan
            scan_mode: 'full' or 'pr'

        Returns:
            Complete ScanResponse with deterministic + optional LLM analysis
        """
        scan_id = str(uuid.uuid4())[:8]
        start_time = time.monotonic()

        logger.info(f"[{scan_id}] Starting {scan_mode} scan of {len(files)} files")

        # ── Step 1: Parse AST for each file ──
        modules: dict[str, ModuleAST] = {}
        for i, f in enumerate(files):
            # Check cache first
            cached = self.cache.get(f.path, f.content)
            if cached:
                modules[f.path] = cached.module_ast
                logger.debug(f"[{scan_id}] Cache hit: {f.path}")
            else:
                module_ast = parse_file(f.content, f.path)
                modules[f.path] = module_ast
                logger.debug(f"[{scan_id}] Parsed: {f.path}")

        # ── Step 2: Build call graph ──
        call_graph = build_call_graph(modules)
        logger.info(
            f"[{scan_id}] Call graph: {len(call_graph.nodes)} nodes, "
            f"{len(call_graph.edges)} edges"
        )

        # ── Step 3: Data flow analysis ──
        data_flow_issues = []
        for file_path, module_ast in modules.items():
            issues = analyze_data_flow(module_ast)
            data_flow_issues.extend(issues)
        logger.info(f"[{scan_id}] Data flow issues: {len(data_flow_issues)}")

        # ── Step 4: Rule engine ──
        rule_result = self.rule_engine.run(modules, call_graph)
        logger.info(
            f"[{scan_id}] Rule violations: {len(rule_result.violations)} "
            f"({rule_result.scan_duration_ms:.1f}ms)"
        )

        # ── Step 5: Test harness (if enabled) ──
        test_failures_json = "[]"
        test_failure_rule_ids: set[str] = set()
        if settings.test_harness_enabled:
            test_results = []
            for module_ast in modules.values():
                for func in module_ast.functions:
                    cases = generate_edge_cases(func)
                    results = await asyncio.to_thread(
                        run_tests, cases, func.body_source, settings.test_harness_timeout
                    )
                    test_results.extend(results)

            failed_tests = [r for r in test_results if not r.passed]
            if failed_tests:
                test_failures_json = json.dumps(
                    [
                        {
                            "function": r.function_name,
                            "description": r.test_description,
                            "error_type": r.error_type,
                            "error_message": r.error_message,
                        }
                        for r in failed_tests
                    ]
                )
            logger.info(
                f"[{scan_id}] Test harness: {len(test_results)} tests, "
                f"{len(failed_tests)} failures"
            )

        # ── Step 6: Risk scoring ──
        risk_breakdown = compute_risk_score(
            rule_result, call_graph, test_failure_rule_ids
        )
        logger.info(f"[{scan_id}] Risk score: {risk_breakdown.total_score}/100")

        # ── Step 7–8: LLM or fallback ──
        llm_used = False
        llm_tokens = 0
        issues: list[Issue] = []

        has_critical_or_high = any(
            v.severity in ("critical", "high")
            or (hasattr(v.severity, "value") and v.severity.value in ("critical", "high"))
            for v in rule_result.violations
        )

        should_use_llm = (
            self.llm_gateway is not None
            and (
                risk_breakdown.total_score > settings.llm_risk_threshold
                or has_critical_or_high
            )
            and rule_result.violations
        )

        if should_use_llm and self.llm_gateway:
            logger.info(f"[{scan_id}] Invoking LLM (risk={risk_breakdown.total_score})")
            self.llm_gateway.reset_token_counter()

            file_paths = list(modules.keys())
            prompt = build_prompt(
                rule_result=rule_result,
                call_graph=call_graph,
                risk_breakdown=risk_breakdown,
                test_failures_json=test_failures_json,
                file_paths=file_paths,
            )

            llm_response = await self.llm_gateway.complete(prompt)
            llm_tokens = llm_response.get("tokens_used", 0)

            if llm_response.get("success"):
                # Validate LLM response
                valid_rule_ids = {v.rule_id for v in rule_result.violations}
                violation_ranges = {
                    v.rule_id: (v.line, v.end_line or v.line)
                    for v in rule_result.violations
                }

                validation = validate_llm_response(
                    parsed=llm_response["parsed"],
                    valid_file_paths=set(file_paths),
                    valid_rule_ids=valid_rule_ids,
                    violation_line_ranges=violation_ranges,
                )

                if validation.valid and validation.response:
                    llm_used = True
                    issues = _merge_llm_with_violations(
                        rule_result.violations,
                        validation.response,
                    )
                    logger.info(f"[{scan_id}] LLM response validated and merged")
                else:
                    logger.warning(
                        f"[{scan_id}] LLM response rejected: {validation.errors}"
                    )
                    issues = generate_fallback_issues(rule_result.violations)
            else:
                logger.warning(
                    f"[{scan_id}] LLM failed: {llm_response.get('error', 'unknown')}"
                )
                issues = generate_fallback_issues(rule_result.violations)
        else:
            issues = generate_fallback_issues(rule_result.violations)
            logger.info(f"[{scan_id}] Using deterministic-only output")

        # ── Step 9: Cache results ──
        for f in files:
            if f.path in modules:
                file_violations = [
                    v for v in rule_result.violations if v.file == f.path
                ]
                self.cache.put(f.path, f.content, modules[f.path], file_violations)

        # ── Assemble response ──
        elapsed_ms = (time.monotonic() - start_time) * 1000

        audit = AuditEntry(
            scan_id=scan_id,
            files_scanned=len(files),
            violations_found=len(rule_result.violations),
            risk_score=risk_breakdown.total_score,
            llm_invoked=llm_used,
            llm_tokens_used=llm_tokens,
            duration_ms=round(elapsed_ms, 2),
            deterministic_only=not llm_used,
        )

        # Build summary
        summary = risk_breakdown.summary
        if scan_mode == "pr":
            summary = f"PR Analysis: {summary}"

        report = ScanReport(
            issues=issues,
            riskScore=risk_breakdown.total_score,
            risk_breakdown=risk_breakdown,
            summary=summary,
            llm_used=llm_used,
            deterministic_only=not llm_used,
            audit=audit,
        )

        response = ScanResponse(
            message="scan_complete",
            scan_id=scan_id,
            report=report,
        )

        logger.info(
            f"[{scan_id}] Scan complete in {elapsed_ms:.0f}ms — "
            f"{len(issues)} issues, score={risk_breakdown.total_score}, "
            f"llm={'yes' if llm_used else 'no'}"
        )

        return response


def _merge_llm_with_violations(violations, llm_response) -> list[Issue]:
    """Merge LLM explanations with deterministic violations."""
    from app.models.llm_models import LLMResponse

    # Index LLM explanations by rule_id
    explanation_map = {}
    if isinstance(llm_response, LLMResponse):
        for exp in llm_response.explanations:
            explanation_map[exp.violation_rule_id] = exp

    issues: list[Issue] = []
    for i, v in enumerate(violations):
        exp = explanation_map.get(v.rule_id)

        patches: list[Patch] = []
        risk_text = v.description
        explanation_text = v.description

        if exp:
            explanation_text = exp.natural_language_explanation or v.description
            risk_text = exp.production_risk_summary or v.description
            for ps in exp.patch_suggestions:
                patches.append(
                    Patch(
                        file=ps.file,
                        start_line=ps.start_line,
                        end_line=ps.end_line,
                        new_code=ps.new_code,
                    )
                )

        issues.append(
            Issue(
                id=f"{v.rule_id}-{i + 1}",
                severity=v.severity.value if hasattr(v.severity, "value") else v.severity,
                file=v.file,
                line=v.line,
                rule_id=v.rule_id,
                issue=v.title,
                explanation=explanation_text,
                risk=risk_text,
                evidence=v.evidence,
                patches=patches,
                testImpact=[],
            )
        )

    return issues
