from __future__ import annotations

import json
from collections.abc import Iterable

from ..schemas import ChecklistEvaluation, ReviewFinding, ReviewInput


STRUCTURED_SECTIONS = {"formula", "table", "algorithm", "figure"}


def semantic_payload(review_input: ReviewInput, max_chars: int) -> dict[str, object]:
    disclosure = review_input.disclosure.model_dump()
    payload: dict[str, object] = {
        "source": {
            "title": review_input.source.title,
            "abstract": review_input.source.abstract,
            "section_titles": list(review_input.source.sections),
        },
        "disclosure": disclosure,
        "evidence": [],
    }
    preferred_ids = _generator_evidence_ids(review_input)
    payload["evidence"] = _evidence_packet(
        review_input,
        preferred_ids=preferred_ids,
        budget=_remaining_budget(payload, max_chars),
    )
    return payload


def revision_payload(
    review_input: ReviewInput,
    findings: list[ReviewFinding],
    max_chars: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "disclosure": review_input.disclosure.model_dump(),
        "findings": [item.model_dump(mode="json") for item in findings],
        "evidence": [],
    }
    finding_ids = [evidence_id for item in findings for evidence_id in item.evidence_ids]
    preferred_ids = [*finding_ids, *_generator_evidence_ids(review_input)]
    payload["evidence"] = _evidence_packet(
        review_input,
        preferred_ids=preferred_ids,
        budget=_remaining_budget(payload, max_chars),
    )
    return payload


def issue_revision_payload(
    review_input: ReviewInput,
    evaluation: ChecklistEvaluation,
    findings: list[ReviewFinding],
    allowed_target_paths: list[str],
    max_chars: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "check": evaluation.model_dump(mode="json"),
        "findings": [item.model_dump(mode="json") for item in findings],
        "allowed_target_paths": allowed_target_paths,
        "editable_content": {
            path: getattr(review_input.disclosure, path)
            for path in allowed_target_paths
        },
        "read_only_disclosure": review_input.disclosure.model_dump(),
        "evidence": [],
    }
    finding_ids = [evidence_id for item in findings for evidence_id in item.evidence_ids]
    preferred_ids = [*finding_ids, *_generator_evidence_ids(review_input)]
    payload["evidence"] = _evidence_packet(
        review_input,
        preferred_ids=preferred_ids,
        budget=_remaining_budget(payload, max_chars),
    )
    return payload


def serialized_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _remaining_budget(payload: dict[str, object], max_chars: int) -> int:
    # Reserve prompt instructions and JSON container overhead while preserving
    # the complete disclosure and findings even when they exceed the budget.
    base_size = len(serialized_payload(payload))
    return max(0, max_chars - base_size - 2_000)


def _generator_evidence_ids(review_input: ReviewInput) -> list[str]:
    metadata = review_input.generator_metadata
    candidates: list[str] = []
    for ids in metadata.get("field_evidence_ids", {}).values():
        if isinstance(ids, list):
            candidates.extend(str(item) for item in ids)
    for ids in metadata.get("evidence_mapping", {}).values():
        if isinstance(ids, list):
            candidates.extend(str(item) for item in ids)
    return list(dict.fromkeys(candidates))


def _evidence_packet(
    review_input: ReviewInput,
    *,
    preferred_ids: Iterable[str],
    budget: int,
) -> list[dict[str, str]]:
    if budget <= 0:
        return []

    by_id = {item.evidence_id: item for item in review_input.evidence}
    ordered = []
    seen: set[str] = set()

    def add(evidence_id: str) -> None:
        item = by_id.get(evidence_id)
        if item is not None and evidence_id not in seen:
            ordered.append(item)
            seen.add(evidence_id)

    for evidence_id in preferred_ids:
        add(evidence_id)

    for item in review_input.evidence:
        if item.section.casefold() in STRUCTURED_SECTIONS:
            add(item.evidence_id)

    represented_sections = {item.section for item in ordered}
    for item in review_input.evidence:
        if item.section not in represented_sections:
            add(item.evidence_id)
            represented_sections.add(item.section)

    for item in review_input.evidence:
        add(item.evidence_id)

    packet: list[dict[str, str]] = []
    used = 2
    for item in ordered:
        entry = {
            "evidence_id": item.evidence_id,
            "source_file": item.source_file,
            "section": item.section,
            "locator": item.locator,
            "text": item.text,
        }
        entry_size = len(json.dumps(entry, ensure_ascii=False)) + 1
        if used + entry_size > budget:
            continue
        packet.append(entry)
        used += entry_size
    return packet
