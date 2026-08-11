from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document

from latex2disclosure.config import Settings
from latex2disclosure.pipeline import DisclosurePipeline
from latex2disclosure.schemas import JobStatus
from latex2disclosure.storage import JobStore


@pytest.mark.asyncio
async def test_offline_pipeline_generates_reviewable_disclosure(tmp_path: Path):
    sample = Path(__file__).parents[1] / "examples" / "sample.tex"
    settings = Settings(L2D_OFFLINE_MODE=True, L2D_DATA_DIR=tmp_path / "data").prepare()
    store = JobStore(settings.data_dir / "jobs")
    pipeline = DisclosurePipeline(settings, store)
    job = pipeline.create(sample.name, sample)
    completed = await pipeline.run(job.job_id)

    assert completed.status == JobStatus.completed
    assert completed.paper is not None
    assert completed.understanding is not None
    assert completed.invention is not None
    assert completed.solution is not None
    assert completed.evidence_package is not None
    assert completed.disclosure is not None
    assert completed.review is None
    assert len(completed.invention.proposed_title) <= 25
    assert len(completed.solution.method_steps) >= 3
    assert set(completed.artifacts) == {"markdown", "docx", "json"}
    assert [event.status for event in completed.events].count("completed") == 7

    snapshot = json.loads(Path(completed.artifacts["json"]).read_text(encoding="utf-8"))
    assert snapshot["status"] == "completed"
    assert snapshot["events"][-1]["stage"] == "stage7_export"
    document = Document(completed.artifacts["docx"])
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "技术交底书" in text
    assert "详细技术方案" in text
    assert "系统实现" in text
    assert "数据与接口" in text
    assert "术语与符号" in text
