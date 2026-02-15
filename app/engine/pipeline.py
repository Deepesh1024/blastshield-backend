"""
Patch Pipeline — Main orchestrator for the patch generation engine.

Full pipeline:
1. Run rule engine → detect violations
2. For each violation: generate patch (LLM or fallback)
3. AST-validate the patch
4. Apply patch to source
5. Re-scan patched source
6. If re-scan passes → accept; else → rollback
7. Multi-pass self-correction loop (max 2 retries)
"""

from __future__ import annotations

import ast
import json
import logging
import time
from typing import Any

from app.config import settings
from app.core.ast_parser import parse_file
from app.core.call_graph import build_call_graph
from app.core.risk_scorer import compute_risk_score
from app.core.rule_engine import RuleEngine
from app.engine.ast_validator import validate_patch_ast
from app.engine.fallback_patches import generate_fallback_patch
from app.engine.patch_applier import apply_function_patch
from app.engine.rescan import rescan_patched_source
from app.engine.rollback_manager import RollbackManager
from app.llm.gateway import LLMGateway
from app.llm.patch_prompt_builder import build_patch_prompt, build_review_prompt
from app.models.ast_models import ModuleAST
from app.models.llm_models import LLMPatchGeneration, LLMReviewVerdict
from app.models.patch_models import PatchFileInput, PatchResult, PatchResponse
from app.models.rule_models import RuleViolation

logger = logging.getLogger("blastshield.engine.pipeline")


class PatchPipeline:
    """
    Main patch generation pipeline orchestrator.

    Ties together: rule engine → LLM/fallback generation → AST validation →
    patch application → re-scan → rollback.
    """

    def __init__(
        self,
        llm_gateway: LLMGateway | None = None,
        max_retries: int | None = None,
        review_enabled: bool | None = None,
    ) -> None:
        self.llm_gateway = llm_gateway
        self.rule_engine = RuleEngine()
        self.rollback_mgr = RollbackManager()
        self.max_retries = max_retries if max_retries is not None else settings.patch_max_retries
        self.review_enabled = review_enabled if review_enabled is not None else settings.patch_review_enabled

    async def run(
        self,
        files: list[PatchFileInput],
        target_rule_ids: list[str] | None = None,
        use_fallback: bool = True,
    ) -> PatchResponse:
        """
        Execute the full patch generation pipeline.

        Args:
            files: Source files to analyze and patch
            target_rule_ids: Optional filter — only patch these rules
            use_fallback: Whether to use deterministic fallbacks if LLM fails

        Returns:
            PatchResponse with all results
        """
        start_time = time.monotonic()
        logger.info(f"Patch pipeline starting for {len(files)} files")

        # ── Step 1: Parse and analyze ──
        modules: dict[str, ModuleAST] = {}
        sources: dict[str, str] = {}
        for f in files:
            modules[f.path] = parse_file(f.content, f.path)
            sources[f.path] = f.content

        call_graph = build_call_graph(modules)
        rule_result = self.rule_engine.run(modules, call_graph)
        risk_breakdown = compute_risk_score(rule_result, call_graph)
        original_risk_score = risk_breakdown.total_score

        logger.info(
            f"Detection: {len(rule_result.violations)} violations, "
            f"risk score {original_risk_score}"
        )

        # Filter violations if target_rule_ids specified
        violations = rule_result.violations
        if target_rule_ids:
            violations = [v for v in violations if v.rule_id in target_rule_ids]
            logger.info(f"Filtered to {len(violations)} violations for rules: {target_rule_ids}")

        # ── Step 2–7: Process each violation ──
        results: list[PatchResult] = []
        current_sources = dict(sources)  # Working copy

        for violation in violations:
            result = await self._process_violation(
                violation=violation,
                sources=current_sources,
                original_risk_score=original_risk_score,
                use_fallback=use_fallback,
            )
            results.append(result)

            # Update working source if patch was applied
            if result.status == "applied" and result.file_path in current_sources:
                current_sources[result.file_path] = result.patched_code if result.patched_code else current_sources[result.file_path]

        # ── Compute final risk score ──
        final_modules: dict[str, ModuleAST] = {}
        for path, source in current_sources.items():
            final_modules[path] = parse_file(source, path)
        final_rule_result = self.rule_engine.run(final_modules)
        final_risk = compute_risk_score(final_rule_result)

        elapsed = (time.monotonic() - start_time) * 1000

        response = PatchResponse(
            message="patch_complete",
            results=results,
            total_violations=len(violations),
            patches_applied=sum(1 for r in results if r.status == "applied"),
            patches_rejected=sum(1 for r in results if r.status == "rejected"),
            patches_rolled_back=sum(1 for r in results if r.status == "rollback"),
            risk_score_before=original_risk_score,
            risk_score_after=final_risk.total_score,
            patched_sources=current_sources,
        )

        logger.info(
            f"Patch pipeline complete in {elapsed:.0f}ms — "
            f"{response.patches_applied}/{response.total_violations} applied, "
            f"risk {original_risk_score} → {final_risk.total_score}"
        )

        return response

    async def _process_violation(
        self,
        violation: RuleViolation,
        sources: dict[str, str],
        original_risk_score: int,
        use_fallback: bool,
    ) -> PatchResult:
        """Process a single violation through the full pipeline."""
        file_path = violation.file
        func_name = violation.affected_function or ""
        source = sources.get(file_path, "")

        result = PatchResult(
            rule_id=violation.rule_id,
            target_function=func_name,
            file_path=file_path,
            risk_score_before=original_risk_score,
        )

        if not source:
            result.status = "failed"
            result.explanation = f"Source not found for {file_path}"
            return result

        # Save snapshot for rollback
        self.rollback_mgr.save_snapshot(file_path, func_name, source)

        # Extract function source
        func_source = _extract_function_source(source, func_name)
        if not func_source:
            func_source = source  # Use full source if function not found

        result.original_code = func_source

        # Get function metadata for validation
        is_async = False
        decorators: list[str] = []
        try:
            module = parse_file(source, file_path)
            for f in module.functions:
                if f.name == func_name or f.qualified_name == func_name:
                    is_async = f.is_async
                    decorators = f.decorators
                    break
            for cls in module.classes:
                for m in cls.methods:
                    if m.name == func_name:
                        is_async = m.is_async
                        decorators = m.decorators
                        break
        except Exception:
            pass

        # ── Try LLM generation with self-correction ──
        patch_applied = False
        for attempt in range(self.max_retries + 1):
            result.llm_attempts = attempt + 1

            # Generate patch
            new_code = await self._generate_patch(
                violation=violation,
                func_source=func_source,
                file_source=source,
                use_fallback=use_fallback and attempt == self.max_retries,
            )

            if new_code is None:
                if attempt < self.max_retries:
                    continue
                result.status = "failed"
                result.explanation = "All patch generation attempts failed"
                return result

            # ── AST Validate ──
            patched_source = apply_function_patch(source, func_name, new_code)
            if patched_source is None:
                result.validation_errors.append("Patch application failed (function not found or syntax error)")
                if attempt < self.max_retries:
                    continue
                result.status = "rejected"
                return result

            verdict = validate_patch_ast(
                original_source=source,
                patched_source=patched_source,
                target_function=func_name,
                is_async=is_async,
                original_decorators=decorators,
            )

            if not verdict.valid:
                result.validation_errors.extend(verdict.errors)
                logger.warning(
                    f"AST validation failed (attempt {attempt + 1}): {verdict.errors}"
                )
                if attempt < self.max_retries:
                    continue
                result.status = "rejected"
                return result

            # ── Multi-pass LLM review ──
            if self.review_enabled and self.llm_gateway and attempt < self.max_retries:
                review_ok = await self._review_patch(violation, func_source, new_code)
                if not review_ok:
                    logger.info(f"LLM review flagged issues (attempt {attempt + 1}), regenerating")
                    continue

            # ── Re-scan ──
            rescan = rescan_patched_source(
                patched_source=patched_source,
                file_path=file_path,
                target_rule_id=violation.rule_id,
                original_risk_score=original_risk_score,
            )

            result.risk_score_after = rescan.risk_score_after

            if rescan.passed:
                result.status = "applied"
                result.patched_code = patched_source
                result.explanation = f"Patch applied successfully. {rescan.details}"
                patch_applied = True
                break
            else:
                logger.warning(f"Re-scan failed (attempt {attempt + 1}): {rescan.details}")
                if rescan.risk_increased:
                    result.status = "rollback"
                    result.explanation = f"Rolled back: {rescan.details}"
                    # Restore original
                    original = self.rollback_mgr.rollback(file_path, func_name)
                    if original:
                        sources[file_path] = original
                    return result

                if attempt < self.max_retries:
                    continue

                result.status = "rejected"
                result.explanation = f"Re-scan failed after {self.max_retries + 1} attempts: {rescan.details}"
                return result

        if not patch_applied and result.status not in ("applied", "rollback", "rejected"):
            result.status = "failed"

        return result

    async def _generate_patch(
        self,
        violation: RuleViolation,
        func_source: str,
        file_source: str,
        use_fallback: bool,
    ) -> str | None:
        """Generate a patch using LLM or fallback."""
        # Try LLM first
        if self.llm_gateway and not use_fallback:
            prompt = build_patch_prompt(
                violation=violation,
                function_source=func_source,
                file_source=file_source,
            )

            llm_response = await self.llm_gateway.complete(prompt)
            if llm_response.get("success") and llm_response.get("parsed"):
                try:
                    patch_gen = LLMPatchGeneration(**llm_response["parsed"])
                    return patch_gen.patch.new_code
                except Exception as e:
                    logger.warning(f"LLM response parsing failed: {e}")

        # Fallback to deterministic template
        if use_fallback:
            func_name = violation.affected_function or ""
            fallback_code = generate_fallback_patch(
                violation.rule_id, func_source, func_name
            )
            if fallback_code:
                logger.info(f"Using deterministic fallback for {violation.rule_id}")
                return fallback_code

        return None

    async def _review_patch(
        self,
        violation: RuleViolation,
        original_code: str,
        patched_code: str,
    ) -> bool:
        """
        Multi-pass self-correction: ask LLM to review its own patch.

        Returns True if patch is safe, False if issues found.
        """
        if not self.llm_gateway:
            return True

        prompt = build_review_prompt(violation, original_code, patched_code)
        response = await self.llm_gateway.complete(prompt)

        if response.get("success") and response.get("parsed"):
            try:
                review = LLMReviewVerdict(**response["parsed"])
                if not review.safe:
                    logger.warning(f"LLM review flagged issues: {review.issues}")
                    return False
                return True
            except Exception as e:
                logger.warning(f"Review response parsing failed: {e}")
                return True  # Don't block on review parse failure

        return True  # Don't block on review failure


def _extract_function_source(source: str, func_name: str) -> str | None:
    """Extract a single function's source code from a file."""
    if not func_name:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                start = node.lineno - 1
                # Include decorators
                if node.decorator_list:
                    start = node.decorator_list[0].lineno - 1
                end = node.end_lineno or node.lineno
                return "\n".join(lines[start:end])

    return None
