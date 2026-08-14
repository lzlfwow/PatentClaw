from __future__ import annotations

import json

from patent_reviewer.agents.context import revision_payload, semantic_payload, serialized_payload
from patent_reviewer.schemas import (
    EvidenceSpan,
    ReviewFinding,
    ReviewInput,
    Severity,
    SourceDocument,
    TechnicalDisclosure,
)


def _large_input() -> ReviewInput:
    disclosure = TechnicalDisclosure(
        invention_title="一种完整测试方法",
        technical_field="数据处理",
        overall_solution="必须完整保留的总体技术方案",
        detailed_steps=["S101，接收输入。", "S102，处理输入。", "S103，输出结果。"],
    )
    evidence = [
        EvidenceSpan(
            evidence_id=f"E{index:04d}",
            source_file="main.tex",
            section="Method" if index % 2 else "Experiments",
            locator=f"chunk {index}",
            text="证据内容" * 200,
        )
        for index in range(1, 300)
    ]
    return ReviewInput(
        generator_job_path="job.json",
        source_path="paper.zip",
        source=SourceDocument(
            root_file="main.tex",
            title="完整论文",
            abstract="摘要",
            sections={"Method": "原文章节" * 20_000},
            plain_text="正文",
        ),
        evidence=evidence,
        disclosure=disclosure,
        generator_metadata={
            "field_evidence_ids": {"overall_solution": ["E0299"]},
            "evidence_mapping": {"步骤": ["E0250"]},
        },
    )


def test_semantic_payload_preserves_disclosure_and_preferred_evidence() -> None:
    payload = semantic_payload(_large_input(), max_chars=20_000)
    encoded = serialized_payload(payload)
    decoded = json.loads(encoded)

    assert decoded["disclosure"]["overall_solution"] == "必须完整保留的总体技术方案"
    assert "sections" not in decoded["source"]
    assert {item["evidence_id"] for item in decoded["evidence"]} >= {"E0299", "E0250"}
    assert len(encoded) <= 20_000


def test_revision_payload_preserves_findings_before_evidence_budget() -> None:
    review_input = _large_input()
    finding = ReviewFinding(
        finding_id="LLM-0001",
        check_id="EN-04",
        dimension="充分公开",
        severity=Severity.major,
        code="DETAIL",
        target_section="技术方案",
        target_path="detailed_steps",
        issue="需要核对实施细节",
        risk="公开不充分",
        evidence_ids=["E0200"],
        suggested_revision="依据证据修订",
    )
    payload = revision_payload(review_input, [finding], max_chars=20_000)
    decoded = json.loads(serialized_payload(payload))

    assert decoded["findings"][0]["finding_id"] == "LLM-0001"
    assert decoded["disclosure"]["invention_title"] == "一种完整测试方法"
    assert "E0200" in {item["evidence_id"] for item in decoded["evidence"]}
