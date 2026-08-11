from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from ..config import Settings
from ..schemas import EvidenceSpan, PipelineJob


T = TypeVar("T", bound=BaseModel)


@dataclass
class AgentContext:
    job: PipelineJob
    settings: Settings
    gateway: "ModelGateway"


class SubAgent(Protocol):
    name: str
    stage: str
    label: str

    async def run(self, context: AgentContext) -> None: ...


class ModelGateway:
    """Thin structured-output gateway; sub-agents remain provider-independent."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            None
            if settings.offline_mode
            else AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                max_retries=settings.openai_max_retries,
                timeout=settings.openai_timeout_seconds,
            )
        )

    async def structured(
        self,
        *,
        model: str,
        output_type: type[T],
        system_prompt: str,
        payload: BaseModel | dict[str, object],
    ) -> T:
        if self.client is None:
            raise RuntimeError("离线模式不能调用模型网关")
        data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        response = await self.client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
            text_format=output_type,
        )
        if response.output_parsed is None:
            raise RuntimeError("模型未返回可解析的结构化结果")
        return response.output_parsed


def sentences(text: str, minimum: int = 16) -> list[str]:
    items = [item.strip(" \t\n-•") for item in re.split(r"(?<=[。！？.!?;；])\s+|\n+", text)]
    return [item for item in items if len(item) >= minimum]


def select_section(job: PipelineJob, keywords: tuple[str, ...]) -> str:
    if not job.paper:
        return ""
    selected = [body for title, body in job.paper.sections.items() if any(key.lower() in title.lower() for key in keywords)]
    return "\n".join(selected)


def compact_evidence(
    job: PipelineJob,
    limit: int = 40,
    *,
    keywords: tuple[str, ...] = (),
    preferred_ids: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    """Return a relevance-ranked, section-diverse evidence packet.

    LaTeX projects commonly contain hundreds of evidence spans. Taking the
    first N spans systematically drops experiments and appendices, so agents
    receive explicit citations first, then keyword matches, section coverage,
    and finally evenly distributed fallbacks from the whole paper.
    """

    if limit <= 0 or not job.evidence:
        return []

    preferred = set(preferred_ids)
    terms = tuple(term.casefold() for term in keywords if term.strip())
    ranked: list[tuple[int, int, EvidenceSpan]] = []
    for index, item in enumerate(job.evidence):
        section = item.section.casefold()
        text = item.text.casefold()
        score = 10_000 if item.evidence_id in preferred else 0
        for term in terms:
            if term in section:
                score += 40
            if term in text:
                score += 12
        ranked.append((score, index, item))

    selected: list[EvidenceSpan] = []
    selected_ids: set[str] = set()

    def add(item: EvidenceSpan) -> None:
        evidence_id = item.evidence_id
        if len(selected) < limit and evidence_id not in selected_ids:
            selected.append(item)
            selected_ids.add(evidence_id)

    evidence_by_id = {item.evidence_id: item for item in job.evidence}
    for evidence_id in preferred_ids:
        item = evidence_by_id.get(evidence_id)
        if item is not None:
            add(item)

    best_by_section: dict[str, tuple[int, int, EvidenceSpan]] = {}
    for entry in ranked:
        item = entry[2]
        current = best_by_section.get(item.section)
        if current is None or (entry[0], -entry[1]) > (current[0], -current[1]):
            best_by_section[item.section] = entry
    section_budget = min(len(best_by_section), max(2, limit // 3))
    section_candidates = sorted(
        best_by_section.values(),
        key=lambda value: (-value[0], value[1]),
    )
    for _, _, item in section_candidates[:section_budget]:
        add(item)

    per_section_cap = max(2, limit // max(2, section_budget))
    per_section_counts: dict[str, int] = {}
    for item in selected:
        per_section_counts[item.section] = per_section_counts.get(item.section, 0) + 1
    for score, _, item in sorted(ranked, key=lambda value: (-value[0], value[1])):
        if score <= 0:
            break
        if per_section_counts.get(item.section, 0) >= per_section_cap:
            continue
        before = len(selected)
        add(item)
        if len(selected) > before:
            per_section_counts[item.section] = per_section_counts.get(item.section, 0) + 1

    remaining = limit - len(selected)
    if remaining > 0:
        step = max(1, len(job.evidence) // remaining)
        for index in range(0, len(job.evidence), step):
            add(job.evidence[index])
    for item in job.evidence:
        add(item)

    return [
        {
            "evidence_id": item.evidence_id,
            "section": item.section,
            "locator": item.locator,
            "text": item.text,
        }
        for item in selected
    ]
