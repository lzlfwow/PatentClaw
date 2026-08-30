from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from ..schemas import ReviewJob
from .docx import write_disclosure_docx
from .markdown import disclosure_markdown, review_markdown


def export_job_bundle(job: ReviewJob, job_dir: Path) -> dict[str, str]:
    artifacts = job_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    figures_dir = artifacts / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    copied_figures = []
    for figure in job.input.patent_figures:
        copied = figure.model_copy(deep=True)
        for field, suffix in (("image_path", ".png"), ("mermaid_path", ".mmd")):
            source_value = getattr(figure, field)
            if not source_value:
                continue
            source = Path(source_value)
            if not source.is_file():
                continue
            destination = figures_dir / f"figure-{figure.figure_no}{suffix}"
            shutil.copy2(source, destination)
            setattr(copied, field, str(destination.resolve()))
        copied_figures.append(copied)
    job.input.patent_figures = copied_figures
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
        "final_figures_dir": figures_dir,
        "final_figures_zip": artifacts / "final_figures.zip",
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
    paths["final_disclosure_markdown"].write_text(
        disclosure_markdown(job.final_disclosure, job.input.patent_figures), encoding="utf-8"
    )
    write_disclosure_docx(job.final_disclosure, paths["final_disclosure_docx"], job.input.patent_figures)
    with zipfile.ZipFile(paths["final_figures_zip"], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(figures_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)
    paths["change_log_json"].write_text(json.dumps([item.model_dump() for item in job.changes], ensure_ascii=False, indent=2), encoding="utf-8")
    paths["final_review_json"].write_text(job.final_report.model_dump_json(indent=2), encoding="utf-8")
    paths["final_review_markdown"].write_text(review_markdown(job.final_report, "技术交底书终审意见"), encoding="utf-8")
    resolved = {key: str(path.resolve()) for key, path in paths.items()}
    job.artifacts = resolved
    paths["job_json"].write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return resolved
