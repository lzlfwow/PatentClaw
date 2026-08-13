from __future__ import annotations

import argparse
import asyncio
import json

import uvicorn

from .pipeline import run_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patent-reviewer", description="中国发明专利技术交底书审查与改稿")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="运行一次审查任务")
    run.add_argument("--generator-job", required=True, help="PatentGenerator job.json、artifacts目录或任务目录")
    run.add_argument("--source", required=True, help="原始LaTeX文件、目录或zip包")
    run.add_argument("--output", default=None, help="输出根目录；默认读取PR_OUTPUT_ROOT")
    run.add_argument("--online", action="store_true", help="启用OpenAI兼容Responses API语义审查与改稿")
    serve_parser = subparsers.add_parser("serve", help="启动HTTP API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8011)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        uvicorn.run("patent_reviewer.api:app", host=args.host, port=args.port)
        return
    job = asyncio.run(run_review(
        generator_path=args.generator_job,
        source_path=args.source,
        output_root=args.output,
        online=args.online,
    ))
    print(json.dumps({
        "job_id": job.job_id,
        "mode": job.mode.value,
        "initial_score": job.initial_report.score,
        "final_score": job.final_report.score,
        "artifacts": job.artifacts,
    }, ensure_ascii=False, indent=2))


def serve() -> None:
    uvicorn.run("patent_reviewer.api:app", host="127.0.0.1", port=8011)


if __name__ == "__main__":
    main()
