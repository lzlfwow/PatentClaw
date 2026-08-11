from __future__ import annotations

from latex2disclosure.agents.base import compact_evidence
from latex2disclosure.schemas import EvidenceSpan, PipelineJob


def test_compact_evidence_retrieves_late_experiment_and_preserves_section_coverage():
    evidence = [
        EvidenceSpan(
            evidence_id=f"E{index:04d}",
            source_file="main.tex",
            section="Introduction" if index < 120 else "Experiments",
            text=(
                f"Background statement {index}."
                if index < 120
                else f"Bootstrap experiment result with accuracy {index}."
            ),
            locator=f"chunk {index}",
        )
        for index in range(1, 141)
    ]
    job = PipelineJob(job_id="test-job", input_name="main.tex", evidence=evidence)

    packet = compact_evidence(
        job,
        12,
        keywords=("experiment", "bootstrap", "accuracy"),
        preferred_ids=("E0137",),
    )

    ids = {item["evidence_id"] for item in packet}
    sections = {item["section"] for item in packet}
    assert "E0137" in ids
    assert "Experiments" in sections
    assert "Introduction" in sections
    assert all("locator" in item for item in packet)
