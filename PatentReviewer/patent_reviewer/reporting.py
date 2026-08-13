from __future__ import annotations

from collections import Counter

from .rules.engine import WEIGHTS
from .schemas import DimensionScore, ReviewFinding, ReviewReport, Severity


def merge_findings(report: ReviewReport, extra: list[ReviewFinding], pass_score: int = 75) -> ReviewReport:
    seen = {(item.dimension, item.target_path, item.issue) for item in report.findings}
    findings = list(report.findings)
    for item in extra:
        key = (item.dimension, item.target_path, item.issue)
        if key not in seen:
            findings.append(item)
            seen.add(key)
    counts = Counter(item.dimension for item in findings)
    dimensions = [DimensionScore(
        dimension=item.dimension,
        score=max(0, 100 - sum(WEIGHTS[finding.severity] for finding in findings if finding.dimension == item.dimension)),
        finding_count=counts[item.dimension],
    ) for item in report.dimensions]
    known = {item.dimension for item in dimensions}
    dimensions.extend(DimensionScore(
        dimension=dimension,
        score=max(0, 100 - sum(WEIGHTS[item.severity] for item in findings if item.dimension == dimension)),
        finding_count=count,
    ) for dimension, count in sorted(counts.items()) if dimension not in known)
    score = max(0, 100 - sum(WEIGHTS[item.severity] for item in findings))
    return report.model_copy(update={
        "score": score,
        "passed": score >= pass_score and not any(item.severity in (Severity.critical, Severity.major) for item in findings),
        "findings": findings,
        "dimensions": dimensions,
    })
