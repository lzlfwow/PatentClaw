from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from patent_reviewer.agents.revision_agent import (
    IssueRevisionDecision,
    apply_issue_patches,
    revise_issue_online,
)
from patent_reviewer.config import Settings
from patent_reviewer.schemas import (
    ChecklistEvaluation,
    CheckStatus,
    EvidenceSpan,
    ReviewDimension,
    ReviewFinding,
    ReviewInput,
    Severity,
    SourceDocument,
    TechnicalDisclosure,
)


def _decision(**overrides) -> IssueRevisionDecision:
    data = {
        "check_id": "WR-03",
        "outcome": "modified",
        "patches": [{
            "target_path": "background",
            "original_fragment": "可能导致结果不稳定",
            "replacement_fragment": "在输入信号缺失时导致结果不稳定",
            "finding_ids": ["F-WR-03"],
        }],
    }
    data.update(overrides)
    return IssueRevisionDecision.model_validate(data)


def test_modified_decision_requires_fragment_patch() -> None:
    with pytest.raises(ValidationError, match="requires at least one"):
        IssueRevisionDecision.model_validate({
            "check_id": "WR-03",
            "outcome": "modified",
            "patches": [],
        })


def test_issue_patch_only_changes_allowed_field_fragment() -> None:
    disclosure = TechnicalDisclosure(
        invention_title="一种测试方法",
        background=["现有方法可能导致结果不稳定。", "其他背景保持不变。"],
        overall_solution="总体方案保持不变。",
    )

    revised, changes = apply_issue_patches(
        disclosure,
        _decision(),
        expected_check_id="WR-03",
        allowed_target_paths=["background"],
        allowed_finding_ids=["F-WR-03"],
        round_number=1,
    )

    assert revised.background == [
        "现有方法在输入信号缺失时导致结果不稳定。",
        "其他背景保持不变。",
    ]
    assert revised.overall_solution == disclosure.overall_solution
    assert changes[0].finding_ids == ["F-WR-03"]
    assert changes[0].before == "可能导致结果不稳定"


def test_issue_patch_rejects_field_owned_by_another_problem() -> None:
    disclosure = TechnicalDisclosure(
        invention_title="一种测试方法",
        background=["现有方法可能导致结果不稳定。"],
    )
    decision = _decision(patches=[{
        "target_path": "invention_title",
        "original_fragment": "测试方法",
        "replacement_fragment": "检测方法",
        "finding_ids": ["F-WR-03"],
    }])

    with pytest.raises(ValueError, match="outside this issue"):
        apply_issue_patches(
            disclosure,
            decision,
            expected_check_id="WR-03",
            allowed_target_paths=["background"],
            allowed_finding_ids=["F-WR-03"],
            round_number=1,
        )


def test_issue_patch_rejects_ambiguous_original_fragment() -> None:
    disclosure = TechnicalDisclosure(
        invention_title="一种测试方法",
        background=["可能导致偏差。", "还可能导致波动。"],
    )
    decision = _decision(patches=[{
        "target_path": "background",
        "original_fragment": "可能导致",
        "replacement_fragment": "在数据缺失时导致",
        "finding_ids": ["F-WR-03"],
    }])

    with pytest.raises(ValueError, match="exactly once"):
        apply_issue_patches(
            disclosure,
            decision,
            expected_check_id="WR-03",
            allowed_target_paths=["background"],
            allowed_finding_ids=["F-WR-03"],
            round_number=1,
        )


@pytest.mark.asyncio
async def test_online_issue_agent_records_rejected_cross_field_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision = IssueRevisionDecision.model_validate({
        "check_id": "WR-03",
        "outcome": "modified",
        "patches": [{
            "target_path": "invention_title",
            "original_fragment": "测试方法",
            "replacement_fragment": "检测方法",
            "finding_ids": ["F-WR-03"],
        }],
    })

    class FakeResponses:
        async def parse(self, **kwargs):
            return SimpleNamespace(output_parsed=decision)

    fake_client = SimpleNamespace(responses=FakeResponses())
    monkeypatch.setattr(
        "patent_reviewer.agents.revision_agent.build_client",
        lambda settings: fake_client,
    )
    review_input = ReviewInput(
        generator_job_path="job.json",
        source_path="paper.tex",
        source=SourceDocument(root_file="paper.tex"),
        evidence=[EvidenceSpan(
            evidence_id="E-1",
            source_file="paper.tex",
            text="现有方法可能导致结果不稳定。",
        )],
        disclosure=TechnicalDisclosure(
            invention_title="一种测试方法",
            background=["现有方法可能导致结果不稳定。"],
        ),
    )
    evaluation = ChecklistEvaluation(
        check_id="WR-03",
        dimension=ReviewDimension.patent_style,
        title="相对与不确定用语边界清楚",
        severity=Severity.minor,
        status=CheckStatus.failed,
        evaluator="rule",
    )
    finding = ReviewFinding(
        finding_id="F-WR-03",
        check_id="WR-03",
        dimension=ReviewDimension.patent_style,
        severity=Severity.minor,
        code="WR-03",
        target_section="背景技术",
        target_path="background",
        issue="存在不确定用语",
        risk="边界不清",
    )

    result = await revise_issue_online(
        review_input,
        evaluation,
        [finding],
        Settings(openai_api_key="test"),
        round_number=1,
    )

    assert result.attempt.outcome == "rejected"
    assert "outside this issue" in result.attempt.reason
    assert result.disclosure == review_input.disclosure
