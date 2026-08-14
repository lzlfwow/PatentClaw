from __future__ import annotations

import pytest
from pydantic import ValidationError

from patent_reviewer.agents.semantic_review_agent import SemanticChecklistResult
from patent_reviewer.checklist import CHECKLIST, SEMANTIC_CHECKS
from patent_reviewer.reporting import recalculate
from patent_reviewer.schemas import (
    ChecklistEvaluation,
    CheckStatus,
    ReviewDimension,
    ReviewReport,
    Severity,
)


def test_fixed_checklist_ids_are_unique_and_cover_all_dimensions() -> None:
    assert len(CHECKLIST) == 30
    assert len({item.check_id for item in CHECKLIST}) == len(CHECKLIST)
    assert {item.dimension for item in CHECKLIST} == set(ReviewDimension)


def test_semantic_response_must_include_every_fixed_semantic_check() -> None:
    checks = [{
        "check_id": item.check_id,
        "status": "pass",
        "reason": "已核对",
    } for item in SEMANTIC_CHECKS]
    SemanticChecklistResult.model_validate({"checks": checks})

    with pytest.raises(ValidationError, match="missing"):
        SemanticChecklistResult.model_validate({"checks": checks[:-1]})


def test_each_check_id_contributes_at_most_one_penalty() -> None:
    checklist = [ChecklistEvaluation(
        check_id="EN-04",
        dimension=ReviewDimension.enablement,
        title="核心算法和运行步骤可重复实施",
        severity=Severity.major,
        status=CheckStatus.failed,
        evaluator="llm",
    )]
    report = ReviewReport(
        legal_baseline="test",
        score=0,
        passed=False,
        checklist=checklist,
    )

    scored = recalculate(report)

    assert scored.score == 90
