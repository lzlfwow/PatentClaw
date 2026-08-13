from __future__ import annotations

from ..schemas import RevisionAction, RevisionPlan, ReviewReport


def build_revision_plan(report: ReviewReport) -> RevisionPlan:
    actions: list[RevisionAction] = []
    blocked: list[RevisionAction] = []
    for index, finding in enumerate(report.findings, start=1):
        action = RevisionAction(
            action_id=f"A-{index:04d}", finding_ids=[finding.finding_id],
            operation="replace" if finding.auto_fixable else "confirm",
            target_path=finding.target_path, before=finding.original_text,
            after=finding.suggested_revision if finding.auto_fixable else "",
            evidence_ids=finding.evidence_ids, reason=finding.issue,
        )
        (actions if finding.auto_fixable else blocked).append(action)
    return RevisionPlan(actions=actions, blocked_actions=blocked)
