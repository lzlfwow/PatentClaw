from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas import EvidenceSpan, ReviewInput, TechnicalDisclosure
from .latex_loader import load_latex_source


def _locate_job(path: Path) -> Path:
    if path.is_file() and path.name == "job.json":
        return path
    candidates = [path / "job.json", path / "artifacts" / "job.json"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Cannot locate Generator job.json from {path}")


def _evidence(item: dict[str, Any]) -> EvidenceSpan:
    return EvidenceSpan(
        evidence_id=str(item.get("evidence_id", "")),
        source_file=str(item.get("source_file", "")),
        section=str(item.get("section", "")),
        text=str(item.get("text", "")),
        locator=str(item.get("locator", "")),
        origin="generator",
    )


def load_review_input(generator_path: str | Path, source_path: str | Path) -> ReviewInput:
    job_path = _locate_job(Path(generator_path))
    data = json.loads(job_path.read_text(encoding="utf-8"))
    disclosure_data = data.get("disclosure")
    if not isinstance(disclosure_data, dict):
        raise ValueError("Generator job.json does not contain a structured disclosure")
    source = load_latex_source(source_path)
    evidence = [_evidence(item) for item in data.get("evidence", []) if isinstance(item, dict)]
    if not evidence:
        for index, (section, text) in enumerate(source.sections.items(), start=1):
            evidence.append(EvidenceSpan(
                evidence_id=f"latex-{index:04d}", source_file=source.root_file,
                section=section, text=text, locator=section, origin="latex"
            ))
    understanding_ids = data.get("understanding", {}).get("evidence_ids", []) if isinstance(data.get("understanding"), dict) else []
    solution_ids = data.get("solution", {}).get("evidence_ids", []) if isinstance(data.get("solution"), dict) else []
    feature_ids = []
    if isinstance(data.get("invention"), dict):
        for feature in data["invention"].get("features", []):
            if isinstance(feature, dict):
                feature_ids.extend(feature.get("evidence_ids", []))
    evidence_mapping = {}
    unsupported_items = []
    if isinstance(data.get("evidence_package"), dict):
        evidence_mapping = data["evidence_package"].get("evidence_mapping", {})
        unsupported_items = data["evidence_package"].get("unsupported_items", [])
    mapped_ids = list(dict.fromkeys(
        evidence_id for ids in evidence_mapping.values() if isinstance(ids, list) for evidence_id in ids
    ))
    field_evidence_ids = {
        "overall_solution": list(dict.fromkeys(solution_ids or understanding_ids)),
        "detailed_steps": list(dict.fromkeys(solution_ids or understanding_ids)),
        "key_innovations": list(dict.fromkeys(feature_ids or solution_ids)),
        "beneficial_effects": list(dict.fromkeys(mapped_ids or understanding_ids)),
        "embodiments": list(dict.fromkeys(mapped_ids or solution_ids)),
    }
    return ReviewInput(
        generator_job_path=str(job_path),
        source_path=str(source_path),
        source=source,
        evidence=evidence,
        disclosure=TechnicalDisclosure.model_validate(disclosure_data),
        generator_metadata={
            "job_id": data.get("job_id"),
            "status": data.get("status"),
            "input_name": data.get("input_name"),
            "metadata": data.get("metadata", {}),
            "field_evidence_ids": field_evidence_ids,
            "evidence_mapping": evidence_mapping,
            "unsupported_items": unsupported_items,
        },
    )
