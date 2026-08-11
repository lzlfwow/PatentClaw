from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import get_settings
from .pipeline import DisclosurePipeline
from .schemas import JobStatus
from .storage import JobStore


settings = get_settings()
store = JobStore(settings.data_dir / "jobs")
pipeline = DisclosurePipeline(settings, store)

app = FastAPI(
    title="LaTeX2Disclosure Agent API",
    version="0.1.0",
    description="LaTeX论文到中文技术交底书的阶段化Sub-Agent后端。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


async def _execute(job_id: str) -> None:
    await pipeline.run(job_id)


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "offline_mode": settings.offline_mode,
        "model_configured": bool(settings.openai_api_key),
        "agents": [
            {"stage": agent.stage, "name": agent.name, "label": agent.label}
            for agent in pipeline.agents
        ],
    }


@app.post("/api/jobs/upload", status_code=202)
async def upload_job(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict[str, str]:
    filename = Path(file.filename or "paper.tex").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".tex", ".zip"}:
        raise HTTPException(status_code=422, detail="仅支持.tex或.zip格式")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="上传文件为空")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"上传文件不能超过{settings.max_upload_mb}MB")
    if not settings.offline_mode and not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="在线模式缺少OPENAI_API_KEY")
    input_root = settings.data_dir / "uploads"
    input_root.mkdir(parents=True, exist_ok=True)
    temporary = input_root / f"pending-{filename}"
    temporary.write_bytes(data)
    job = pipeline.create(filename, temporary)
    final_path = input_root / f"{job.job_id}-{filename}"
    temporary.replace(final_path)
    job.metadata["input_path"] = str(final_path.resolve())
    store.save(job)
    background_tasks.add_task(_execute, job.job_id)
    return {"job_id": job.job_id, "status": job.status.value}


@app.get("/api/jobs")
async def list_jobs() -> list[dict[str, object]]:
    return [
        {
            "job_id": job.job_id,
            "status": job.status,
            "input_name": job.input_name,
            "title": job.paper.title if job.paper else None,
            "score": job.review.score if job.review else None,
            "updated_at": job.updated_at,
        }
        for job in store.list()
    ]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.get("/api/jobs/{job_id}/artifacts/{kind}")
async def get_artifact(job_id: str, kind: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status != JobStatus.completed:
        raise HTTPException(status_code=409, detail="任务尚未完成")
    value = job.artifacts.get(kind)
    if not value:
        raise HTTPException(status_code=404, detail="产物不存在")
    path = Path(value).resolve()
    allowed_root = (settings.data_dir / job_id / "artifacts").resolve()
    if allowed_root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="产物路径无效")
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream", filename=path.name)

