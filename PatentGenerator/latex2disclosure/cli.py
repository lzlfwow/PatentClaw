from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import uvicorn

from .config import get_settings
from .pipeline import DisclosurePipeline
from .storage import JobStore


def main() -> None:
    parser = argparse.ArgumentParser(description="将LaTeX论文转换为中文技术交底书")
    parser.add_argument("input", type=Path, help=".tex文件、LaTeX工程.zip或工程目录")
    args = parser.parse_args()
    settings = get_settings()
    store = JobStore(settings.data_dir / "jobs")
    pipeline = DisclosurePipeline(settings, store)
    job = pipeline.create(args.input.name, args.input)
    completed = asyncio.run(pipeline.run(job.job_id))
    if completed.status.value != "completed":
        raise SystemExit(completed.error or "任务失败")
    print(f"任务完成：{completed.job_id}")
    for kind, path in completed.artifacts.items():
        print(f"{kind}: {path}")


def serve() -> None:
    uvicorn.run("latex2disclosure.api:app", host="127.0.0.1", port=8100)


if __name__ == "__main__":
    main()

