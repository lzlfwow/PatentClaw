from __future__ import annotations

import os
from pathlib import Path

from .schemas import PipelineJob


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def save(self, job: PipelineJob) -> None:
        target = self.path(job.job_id)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, target)

    def get(self, job_id: str) -> PipelineJob | None:
        target = self.path(job_id)
        if not target.exists():
            return None
        return PipelineJob.model_validate_json(target.read_text(encoding="utf-8"))

    def list(self) -> list[PipelineJob]:
        jobs: list[PipelineJob] = []
        for path in self.root.glob("*.json"):
            try:
                jobs.append(PipelineJob.model_validate_json(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
        return sorted(jobs, key=lambda item: item.updated_at, reverse=True)

