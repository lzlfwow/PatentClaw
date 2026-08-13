from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .agents import revise_disclosure_online, semantic_review_online
from .config import Settings, get_settings
from .exporters import export_job_bundle
from .ingestion.generator_adapter import load_review_input
from .ingestion.input_validator import validate_review_input
from .policies import load_policy
from .reporting import merge_findings
from .revision import apply_revision_plan, build_revision_plan
from .rules import RuleEngine
from .schemas import ChangeRecord, ReviewJob, ReviewMode


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
    report = engine.review(review_input)
    if online:
        semantic = await semantic_review_online(review_input, settings)
        report = merge_findings(report, semantic, int(policy.get("pass_score", 75)))
    else:
        report.limitations.append("离线模式未执行大模型语义核查；事实一致性、无依据扩写和复杂单一性须结合在线模式或人工复核。")
    plan = build_revision_plan(report)

    if online:
        revised = await revise_disclosure_online(review_input, report, settings)
        final_disclosure = revised.disclosure
        changes = _diff_disclosures(review_input.disclosure.model_dump(), final_disclosure.model_dump())
        unresolved = revised.unresolved_finding_ids
    else:
        final_disclosure, changes = apply_revision_plan(review_input.disclosure, plan)
        unresolved = [action.finding_ids[0] for action in plan.blocked_actions]

    final_input = review_input.model_copy(update={"disclosure": final_disclosure})
    final_report = engine.review(final_input)
    if online:
        final_semantic = await semantic_review_online(final_input, settings)
        final_report = merge_findings(final_report, final_semantic, int(policy.get("pass_score", 75)))
    else:
        final_report.limitations.append("离线模式未执行大模型语义终审；当前终审结论仅表示未发现额外的确定性规则问题。")
    root = Path(output_root) if output_root is not None else settings.output_root
    job = ReviewJob(
        job_id=f"review-{uuid4().hex[:12]}", mode=ReviewMode.online if online else ReviewMode.offline,
        input=review_input, initial_report=report, revision_plan=plan,
        final_disclosure=final_disclosure, final_report=final_report, changes=changes,
        completed_at=datetime.now(timezone.utc),
        metadata={"policy_id": policy.get("policy_id"), "model": settings.openai_model if online else None,
                  "unresolved_finding_ids": unresolved},
    )
    export_job_bundle(job, root / job.job_id)
    return job


def _diff_disclosures(before: dict, after: dict) -> list[ChangeRecord]:
    changes = []
    for field in before:
        if before[field] == after.get(field):
            continue
        changes.append(ChangeRecord(
            action_id=f"LLM-{len(changes)+1:04d}", target_path=field,
            before=_stringify(before[field]), after=_stringify(after.get(field)), finding_ids=[],
        ))
    return changes


def _stringify(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value or "")
