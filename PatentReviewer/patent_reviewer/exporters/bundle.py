from __future__ import annotations

import json
from pathlib import Path

from ..schemas import ReviewJob
from .docx import write_disclosure_docx
from .markdown import disclosure_markdown, review_markdown


def export_job_bundle(job: ReviewJob, job_dir: Path) -> dict[str, str]:
    artifacts = job_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    paths = {
        "initial_review_json": artifacts / "initial_review.json",
        "initial_review_markdown": artifacts / "initial_review.md",
        "revision_plan_json": artifacts / "revision_plan.json",
        "revision_attempts_json": artifacts / "revision_attempts.json",
        "final_disclosure_json": artifacts / "final_disclosure.json",
        "final_disclosure_markdown": artifacts / "final_disclosure.md",
        "final_disclosure_docx": artifacts / "final_disclosure.docx",
        "change_log_json": artifacts / "change_log.json",
        "final_review_json": artifacts / "final_review.json",
        "final_review_markdown": artifacts / "final_review.md",
        "job_json": artifacts / "job.json",
    }
    paths["initial_review_json"].write_text(job.initial_report.model_dump_json(indent=2), encoding="utf-8")
    paths["initial_review_markdown"].write_text(review_markdown(job.initial_report, "技术交底书初审意见"), encoding="utf-8")
    paths["revision_plan_json"].write_text(job.revision_plan.model_dump_json(indent=2), encoding="utf-8")
    paths["revision_attempts_json"].write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in job.revision_attempts],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths["final_disclosure_json"].write_text(job.final_disclosure.model_dump_json(indent=2), encoding="utf-8")
    paths["final_disclosure_markdown"].write_text(disclosure_markdown(job.final_disclosure), encoding="utf-8")
    write_disclosure_docx(job.final_disclosure, paths["final_disclosure_docx"])
    paths["change_log_json"].write_text(json.dumps([item.model_dump() for item in job.changes], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["final_review_json"].write_text(job.final_report.model_dump_json(indent=2), encoding="utf-8")
    paths["final_review_markdown"].write_text(review_markdown(job.final_report, "技术交底书终审意见"), encoding="utf-8")
    resolved = {key: str(path.resolve()) for key, path in paths.items()}
    job.artifacts = resolved
    paths["job_json"].write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return resolved
