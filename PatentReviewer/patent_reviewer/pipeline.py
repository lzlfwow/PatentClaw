from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .agents import revise_issue_online, semantic_review_online
from .checklist import CHECKLIST_VERSION
from .config import Settings, get_settings
from .exporters import export_job_bundle
from .ingestion.generator_adapter import load_review_input
from .ingestion.input_validator import validate_review_input
from .policies import load_policy
from .reporting import FAILING_STATUSES, add_resolutions, merge_semantic_results
from .revision import apply_revision_plan, build_revision_plan
from .rules import RuleEngine
from .schemas import (
    IssueRevisionAttempt,
    ReviewInput,
    ReviewJob,
    ReviewMode,
    ReviewReport,
    TechnicalDisclosure,
)


async def run_review(generator_path: str | Path, source_path: str | Path,
                     output_root: str | Path | None = None, online: bool = False,
                     settings: Settings | None = None) -> ReviewJob:
    settings = settings or get_settings()
    online = online or settings.enable_semantic_review
    review_input = load_review_input(generator_path, source_path)
    errors = validate_review_input(review_input)
    if errors:
        raise ValueError("; ".join(errors))

    policy = load_policy()
    engine = RuleEngine(policy)
    pass_score = int(policy.get("pass_score", 75))
    report = engine.review(review_input)
    if online:
        report = await _online_review(review_input, engine, settings, pass_score)
    else:
        report.limitations.append("离线模式未执行大模型语义核查；事实一致性、无依据扩写和复杂单一性须结合在线模式或人工复核。")
    plan = build_revision_plan(report)

    revision_attempts: list[IssueRevisionAttempt] = []
    termination_reason = "offline"
    revision_rounds = 0
    if online:
        current_input = review_input
        current_report = report
        changes = []
        termination_reason = "max_rounds_reached"
        for round_number in range(1, settings.max_revision_rounds + 1):
            failed_checks = [
                item for item in current_report.checklist
                if item.status in FAILING_STATUSES
            ]
            if not failed_checks:
                termination_reason = "all_checks_resolved"
                break

            revision_rounds = round_number
            round_change_count = 0
            for evaluation in failed_checks:
                findings = [
                    item for item in current_report.findings
                    if item.check_id == evaluation.check_id
                ]
                try:
                    result = await revise_issue_online(
                        current_input,
                        evaluation,
                        findings,
                        settings,
                        round_number,
                    )
                except Exception as exc:  # Keep one failed issue agent from aborting all other issues.
                    result = None
                    revision_attempts.append(IssueRevisionAttempt(
                        round_number=round_number,
                        check_id=evaluation.check_id,
                        finding_ids=[item.finding_id for item in findings],
                        allowed_target_paths=list(dict.fromkeys(
                            item.target_path for item in findings
                            if item.target_path in TechnicalDisclosure.model_fields
                        )),
                        outcome="rejected",
                        reason=f"Issue revision agent failed: {exc}",
                    ))
                    continue

                revision_attempts.append(result.attempt)
                if not result.attempt.changes:
                    continue
                round_change_count += len(result.attempt.changes)
                changes.extend(result.attempt.changes)
                current_input = current_input.model_copy(update={
                    "disclosure": result.disclosure,
                })

            if round_change_count == 0:
                termination_reason = "no_safe_changes"
                break
            current_report = await _online_review(
                current_input, engine, settings, pass_score,
            )

        if not any(item.status in FAILING_STATUSES for item in current_report.checklist):
            termination_reason = "all_checks_resolved"

        final_disclosure = current_input.disclosure
        final_report = current_report
    else:
        final_disclosure, changes = apply_revision_plan(review_input.disclosure, plan)
        final_input = review_input.model_copy(update={"disclosure": final_disclosure})
        final_report = engine.review(final_input)
        final_report.limitations.append("离线模式未执行大模型语义终审；当前终审结论仅表示未发现额外的确定性规则问题。")
    final_report = add_resolutions(report, final_report)
    unresolved_findings = [
        item.finding_id for item in final_report.findings
        if any(
            check.check_id == item.check_id and check.status in FAILING_STATUSES
            for check in final_report.checklist
        )
    ]
    unresolved_checks = [
        item.check_id for item in final_report.checklist
        if item.status in FAILING_STATUSES
    ]
    root = Path(output_root) if output_root is not None else settings.output_root
    job = ReviewJob(
        job_id=f"review-{uuid4().hex[:12]}", mode=ReviewMode.online if online else ReviewMode.offline,
        input=review_input, initial_report=report, revision_plan=plan,
        final_disclosure=final_disclosure, final_report=final_report, changes=changes,
        revision_attempts=revision_attempts,
        completed_at=datetime.now(timezone.utc),
        metadata={"policy_id": policy.get("policy_id"), "checklist_version": CHECKLIST_VERSION,
                  "model": settings.openai_model if online else None,
                  "max_revision_rounds": settings.max_revision_rounds if online else 0,
                  "revision_rounds": revision_rounds,
                  "revision_termination_reason": termination_reason,
                  "unresolved_check_ids": unresolved_checks,
                  "unresolved_finding_ids": unresolved_findings},
    )
    export_job_bundle(job, root / job.job_id)
    return job


async def _online_review(
    review_input: ReviewInput,
    engine: RuleEngine,
    settings: Settings,
    pass_score: int,
) -> ReviewReport:
    report = engine.review(review_input)
    semantic = await semantic_review_online(review_input, settings)
    return merge_semantic_results(
        report,
        semantic.evaluations,
        semantic.findings,
        pass_score,
    )
