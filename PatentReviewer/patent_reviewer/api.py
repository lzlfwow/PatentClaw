from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .pipeline import run_review

app = FastAPI(title="PatentReviewer", version="0.1.0")


class ReviewRequest(BaseModel):
    generator_job_path: str
    source_path: str
    output_root: str | None = None
    online: bool = False


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reviews")
async def create_review(request: ReviewRequest) -> dict:
    try:
        job = await run_review(
            generator_path=request.generator_job_path,
            source_path=request.source_path,
            output_root=request.output_root,
            online=request.online,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "job_id": job.job_id,
        "mode": job.mode.value,
        "initial_score": job.initial_report.score,
        "final_score": job.final_report.score,
        "passed": job.final_report.passed,
        "artifacts": job.artifacts,
    }
