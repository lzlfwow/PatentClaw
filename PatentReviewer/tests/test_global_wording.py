from __future__ import annotations

from patent_reviewer.reporting import expand_occurrence_findings
from patent_reviewer.revision.applier import apply_global_wording_replacements
from patent_reviewer.schemas import (
    CheckStatus,
    ChecklistEvaluation,
    ReviewDimension,
    ReviewFinding,
    ReviewReport,
    Severity,
    TechnicalDisclosure,
)


def _report(original: str) -> ReviewReport:
    finding = ReviewFinding(
        finding_id="F-WR-01",
        check_id="WR-01",
        dimension=ReviewDimension.patent_style,
        severity=Severity.minor,
        code="WR-01",
        target_section="背景技术",
        target_path="background",
        original_text=original,
        issue="存在论文式表述",
        risk="文体不规范",
    )
    return ReviewReport(
        legal_baseline="test",
        score=96,
        passed=False,
        findings=[finding],
        checklist=[ChecklistEvaluation(
            check_id="WR-01", dimension=ReviewDimension.patent_style,
            title="使用专利技术文体", severity=Severity.minor,
            status=CheckStatus.failed, evaluator="rule",
        )],
    )


def test_wording_finding_is_split_into_exact_occurrences() -> None:
    disclosure = TechnicalDisclosure(
        background=["本文提出方法。本文验证效果。"],
    )
    report = expand_occurrence_findings(_report("本文"), disclosure)
    assert [item.finding_id for item in report.findings] == ["F-WR-01-O001", "F-WR-01-O002"]
    assert all(item.original_text == "本文" for item in report.findings)


def test_safe_patent_voice_replacement_is_global_and_logged_per_field() -> None:
    disclosure = TechnicalDisclosure(
        background=["本文提出方法。本文验证效果。"],
        beneficial_effects=["本文取得结果。"],
        implementation_boundaries=["本文不涉及主干微调。"],
    )
    revised, changes = apply_global_wording_replacements(
        disclosure,
        allowed_paths=list(TechnicalDisclosure.model_fields),
        finding_ids=["F-WR-01-O001", "F-WR-01-O002"],
        round_number=1,
    )
    assert revised.background == ["本发明提出方法。本发明验证效果。"]
    assert revised.beneficial_effects == ["本发明取得结果。"]
    assert revised.implementation_boundaries == ["本发明不涉及主干微调。"]
    assert {item.target_path for item in changes} == {
        "background", "beneficial_effects", "implementation_boundaries",
    }
