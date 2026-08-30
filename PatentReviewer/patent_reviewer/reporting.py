from __future__ import annotations

from collections import Counter
import re

from .checklist import CHECKLIST, CHECKS_BY_ID, SEVERITY_WEIGHTS
from .schemas import (
    ChecklistEvaluation,
    CheckStatus,
    DimensionScore,
    ReviewFinding,
    ReviewReport,
    Severity,
    TechnicalDisclosure,
)


FAILING_STATUSES = {CheckStatus.failed, CheckStatus.needs_human_review}


def expand_occurrence_findings(
    report: ReviewReport,
    disclosure: TechnicalDisclosure,
) -> ReviewReport:
    """Split multi-occurrence wording findings into exact, independently editable findings."""

    expanded: list[ReviewFinding] = []
    for finding in report.findings:
        if finding.check_id not in {"WR-01", "WR-03"} or not finding.original_text:
            expanded.append(finding)
            continue
        value = getattr(disclosure, finding.target_path, None)
        text = "\n".join(value) if isinstance(value, list) else str(value or "")
        terms = [term.strip() for term in re.split(r"[、，,；;]", finding.original_text) if term.strip()]
        occurrences: list[str] = []
        for term in terms:
            occurrences.extend([term] * len(re.findall(re.escape(term), text, flags=re.IGNORECASE)))
        if len(occurrences) <= 1:
            expanded.append(finding)
            continue
        for index, term in enumerate(occurrences, start=1):
            expanded.append(finding.model_copy(update={
                "finding_id": f"{finding.finding_id}-O{index:03d}",
                "original_text": term,
                "issue": f"{finding.issue}（第{index}处）",
            }))
    return report.model_copy(update={"findings": expanded})


def rule_checklist(findings: list[ReviewFinding]) -> list[ChecklistEvaluation]:
    failed_ids = {item.check_id for item in findings}
    return [ChecklistEvaluation(
        check_id=spec.check_id,
        dimension=spec.dimension,
        title=spec.title,
        severity=spec.severity,
        status=(
            CheckStatus.failed if spec.check_id in failed_ids
            else CheckStatus.passed if spec.evaluator == "rule"
            else CheckStatus.not_assessed
        ),
        evaluator=spec.evaluator,
    ) for spec in CHECKLIST]


def merge_semantic_results(
    report: ReviewReport,
    evaluations: list[ChecklistEvaluation],
    findings: list[ReviewFinding],
    pass_score: int = 75,
) -> ReviewReport:
    semantic_by_id = {item.check_id: item for item in evaluations}
    checklist = [semantic_by_id.get(item.check_id, item) for item in report.checklist]
    merged_findings = _deduplicate_findings([*report.findings, *findings])
    return recalculate(report.model_copy(update={
        "findings": merged_findings,
        "checklist": checklist,
    }), pass_score)


def recalculate(report: ReviewReport, pass_score: int = 75) -> ReviewReport:
    failed = [item for item in report.checklist if item.status in FAILING_STATUSES]
    score = max(0, 100 - sum(SEVERITY_WEIGHTS[item.severity] for item in failed))
    counts = Counter(item.dimension for item in failed)
    dimensions = [DimensionScore(
        dimension=dimension,
        score=max(0, 100 - sum(
            SEVERITY_WEIGHTS[item.severity]
            for item in failed if item.dimension == dimension
        )),
        finding_count=counts[dimension],
    ) for dimension in dict.fromkeys(spec.dimension for spec in CHECKLIST)]
    fully_assessed = all(item.status != CheckStatus.not_assessed for item in report.checklist)
    blocking = any(item.severity in (Severity.critical, Severity.major) for item in failed)
    return report.model_copy(update={
        "score": score,
        "passed": fully_assessed and score >= pass_score and not blocking,
        "dimensions": dimensions,
    })


def add_resolutions(initial: ReviewReport, final: ReviewReport) -> ReviewReport:
    initial_by_id = {item.check_id: item for item in initial.checklist}
    resolved = []
    for item in final.checklist:
        before = initial_by_id[item.check_id].status
        before_failed = before in FAILING_STATUSES
        after_failed = item.status in FAILING_STATUSES
        if before_failed and not after_failed:
            resolution = "resolved"
        elif before_failed and after_failed:
            resolution = "unchanged"
        elif not before_failed and after_failed:
            resolution = "new_failure" if before != CheckStatus.not_assessed else "regressed"
        else:
            resolution = "unchanged"
        resolved.append(item.model_copy(update={"resolution": resolution}))
    return final.model_copy(update={"checklist": resolved})


def _deduplicate_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    # Findings may retain multiple affected fields. Scoring still occurs once
    # per check_id through the checklist status.
    selected: dict[tuple[str, str, str], ReviewFinding] = {}
    for finding in findings:
        key = (finding.check_id, finding.target_path, finding.issue)
        selected.setdefault(key, finding)
    order = {item.check_id: index for index, item in enumerate(CHECKLIST)}
    return sorted(selected.values(), key=lambda item: (order[item.check_id], item.target_path, item.issue))
