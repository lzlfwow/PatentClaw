"""Build the static data blob powering example.html.

The showcase page is a plain static file with no build step and no runtime
fetch, so the real run data is baked into a JS global. Everything this script
writes stays inside web/; the run directory it reads is an external input and
is never modified. Re-run after producing a new reference run:

    python web/tools/build_example_data.py

Paths default relative to this file, so it works from any working directory.
Point --data elsewhere if the run output does not sit at <repo>/patentclaw_data.

Source layout expected under --data (read-only):
    <generator>/jobs/<job_id>.json          PatentGenerator job record
    <generator>/<job_id>/artifacts/*.docx   generator export (media probe)
    review-*/artifacts/*.json               PatentReviewer artifacts
"""

from __future__ import annotations

import argparse
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

WEB_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT = WEB_DIR / "example-data.js"
DEFAULT_DATA = WEB_DIR.parent / "patentclaw_data"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def docx_media_count(path: Path) -> int:
    """Count embedded raster/vector figures in a DOCX (excludes thumbnails)."""
    if not path.exists():
        return 0
    with zipfile.ZipFile(path) as archive:
        return sum(
            1
            for name in archive.namelist()
            if name.startswith("word/media/")
        )


def find_one(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"no match for {pattern!r} under {root}")
    return matches[0]


def duration_seconds(start: str, end: str) -> int | None:
    try:
        fmt = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int((fmt(end) - fmt(start)).total_seconds())
    except (ValueError, AttributeError):
        return None


def compact_finding(finding: dict) -> dict:
    return {
        "finding_id": finding.get("finding_id"),
        "check_id": finding.get("check_id"),
        "dimension": finding.get("dimension"),
        "severity": finding.get("severity"),
        "target_section": finding.get("target_section"),
        "target_path": finding.get("target_path"),
        "issue": finding.get("issue"),
        "risk": finding.get("risk"),
        "suggested_revision": finding.get("suggested_revision"),
        "evidence_ids": finding.get("evidence_ids") or [],
        "auto_fixable": finding.get("auto_fixable"),
        "requires_inventor_confirmation": finding.get("requires_inventor_confirmation"),
        "confidence": finding.get("confidence"),
        "source": finding.get("source"),
    }


def status_counts(checklist: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in checklist:
        status = item.get("status") or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def build(data_dir: Path) -> dict:
    generator_root = find_one(data_dir, "*generator*")
    generator_job_path = find_one(generator_root, "jobs/*.json")
    generator_job = load_json(generator_job_path)
    job_id = generator_job["job_id"]

    review_root = find_one(data_dir, "review-*")
    artifacts = review_root / "artifacts"
    initial_review = load_json(artifacts / "initial_review.json")
    final_review = load_json(artifacts / "final_review.json")
    final_disclosure = load_json(artifacts / "final_disclosure.json")
    revision_attempts = load_json(artifacts / "revision_attempts.json")
    review_job = load_json(artifacts / "job.json")

    paper = generator_job["paper"]
    generator_meta = generator_job.get("metadata") or {}
    review_meta = review_job.get("metadata") or {}
    evidence_package = generator_job.get("evidence_package") or {}

    generator_docx = (
        generator_root / job_id / "artifacts" / "technical_disclosure.docx"
    )
    reviewer_docx = artifacts / "final_disclosure.docx"

    # Pair each fixed-checklist entry with its initial and final status so the
    # page can render resolved / unchanged transitions without re-deriving them.
    initial_by_id = {item["check_id"]: item for item in initial_review["checklist"]}
    checklist = []
    for item in final_review["checklist"]:
        before = initial_by_id.get(item["check_id"], {})
        checklist.append(
            {
                "check_id": item["check_id"],
                "dimension": item.get("dimension"),
                "title": item.get("title"),
                "severity": item.get("severity"),
                "evaluator": item.get("evaluator"),
                "initial_status": before.get("status"),
                "final_status": item.get("status"),
                "resolution": item.get("resolution"),
                "initial_reason": before.get("reason") or "",
                "final_reason": item.get("reason") or "",
            }
        )

    return {
        "meta": {
            "generator_job_id": job_id,
            "review_job_id": review_job.get("job_id"),
            "input_name": generator_job.get("input_name"),
            "model": generator_meta.get("model"),
            "offline_mode": generator_meta.get("offline_mode"),
            "agent_sequence": generator_meta.get("agent_sequence") or [],
            "review_mode": review_job.get("mode"),
            "policy_id": review_meta.get("policy_id"),
            "checklist_version": review_meta.get("checklist_version"),
            "max_revision_rounds": review_meta.get("max_revision_rounds"),
            "revision_rounds": review_meta.get("revision_rounds"),
            "revision_termination_reason": review_meta.get(
                "revision_termination_reason"
            ),
            "generator_created_at": generator_job.get("created_at"),
            "generator_updated_at": generator_job.get("updated_at"),
            "generator_seconds": duration_seconds(
                generator_job.get("created_at", ""),
                generator_job.get("updated_at", ""),
            ),
        },
        "source": {
            "title": paper.get("title"),
            "abstract": paper.get("abstract"),
            "root_file": paper.get("root_file"),
            "section_titles": list(paper.get("sections") or {}),
            "counts": {
                "source_files": len(paper.get("source_files") or []),
                "sections": len(paper.get("sections") or {}),
                "equations": len(paper.get("equations") or []),
                "tables": len(paper.get("tables") or []),
                "algorithms": len(paper.get("algorithms") or []),
                "figures": len(paper.get("figures") or []),
                "evidence": len(generator_job.get("evidence") or []),
            },
            "figures": [
                {
                    "label": figure.get("label"),
                    "caption": figure.get("caption"),
                    "asset_file": Path(figure.get("asset_path", "")).name,
                }
                for figure in paper.get("figures") or []
            ],
        },
        "disclosure": final_disclosure,
        "review": {
            "legal_baseline": final_review.get("legal_baseline"),
            "limitations": final_review.get("limitations") or [],
            "human_review_checklist": final_review.get("human_review_checklist") or [],
            "initial": {
                "score": initial_review.get("score"),
                "passed": initial_review.get("passed"),
                "counts": status_counts(initial_review["checklist"]),
                "findings": [
                    compact_finding(f) for f in initial_review.get("findings") or []
                ],
            },
            "final": {
                "score": final_review.get("score"),
                "passed": final_review.get("passed"),
                "counts": status_counts(final_review["checklist"]),
                "findings": [
                    compact_finding(f) for f in final_review.get("findings") or []
                ],
                "dimensions": final_review.get("dimensions") or [],
            },
            "checklist": checklist,
        },
        "revision": {
            "attempts": [
                {
                    "round_number": attempt.get("round_number"),
                    "check_id": attempt.get("check_id"),
                    "outcome": attempt.get("outcome"),
                    "reason": attempt.get("reason"),
                    "allowed_target_paths": attempt.get("allowed_target_paths") or [],
                    "requested_materials": attempt.get("requested_materials") or [],
                    "evidence_ids": attempt.get("evidence_ids") or [],
                    "changes": attempt.get("changes") or [],
                }
                for attempt in revision_attempts
            ],
            "unresolved_check_ids": review_meta.get("unresolved_check_ids") or [],
        },
        "figures_status": {
            "figure_plan": evidence_package.get("figure_plan") or [],
            "generator_drawings": (generator_job.get("disclosure") or {}).get(
                "drawing_descriptions"
            )
            or [],
            "drawing_descriptions": final_disclosure.get("drawing_descriptions") or [],
            "generator_docx_media": docx_media_count(generator_docx),
            "reviewer_docx_media": docx_media_count(reviewer_docx),
            "paper_figure_count": len(paper.get("figures") or []),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        help=f"run output to read, never written to (default: {DEFAULT_DATA})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"JS file receiving window.PATENTCLAW_EXAMPLE (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()

    if not args.data.is_dir():
        parser.error(
            f"run output not found: {args.data}\n"
            "This directory is an external input; pass --data <dir> to point at it."
        )

    payload = build(args.data)
    body = json.dumps(payload, ensure_ascii=False, indent=1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "/* Generated by web/tools/build_example_data.py — do not edit by hand. */\n"
        f"window.PATENTCLAW_EXAMPLE = {body};\n",
        encoding="utf-8",
    )

    counts = payload["source"]["counts"]
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.1f} KB)")
    print(
        f"  evidence={counts['evidence']} figures={counts['figures']} "
        f"checks={len(payload['review']['checklist'])} "
        f"attempts={len(payload['revision']['attempts'])}"
    )


if __name__ == "__main__":
    main()
