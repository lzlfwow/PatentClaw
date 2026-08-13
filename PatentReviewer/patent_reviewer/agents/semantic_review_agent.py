from __future__ import annotations

import json

from pydantic import BaseModel, Field

from ..config import Settings
from ..schemas import ReviewFinding, ReviewInput, Severity
from .client import build_client


class SemanticFinding(BaseModel):
    dimension: str
    severity: Severity
    code: str
    target_section: str
    target_path: str
    original_text: str = ""
    issue: str
    risk: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_revision: str = ""
    requires_inventor_confirmation: bool = False
    confidence: float = Field(default=0.8, ge=0, le=1)


class SemanticReviewResult(BaseModel):
    findings: list[SemanticFinding] = Field(default_factory=list)


async def semantic_review_online(review_input: ReviewInput, settings: Settings) -> list[ReviewFinding]:
    evidence = [item.model_dump() for item in review_input.evidence]
    payload = {
        "source": {"title": review_input.source.title, "abstract": review_input.source.abstract,
                   "sections": review_input.source.sections},
        "evidence": evidence,
        "disclosure": review_input.disclosure.model_dump(),
    }
    prompt = f"""你是中国发明专利技术交底书的审查助手。基于输入证据逐项审查，不进行新颖性或创造性结论。
重点检查：原文事实一致性、问题-方案-效果闭环、必要技术特征、充分公开、权利要求支持准备、单一性、术语与附图一致性；
若涉及AI/算法，额外检查技术问题、技术手段、技术效果、输入输出关系、模型结构、训练/推理步骤以及算法特征与技术效果的因果关系。
任何事实性修改必须引用 evidence_id；无证据时建议只能标记需发明人确认，不能补造参数、部件、步骤或效果。
target_path 必须是交底书顶层字段名。只输出具有实际修改价值且置信度不低于0.65的问题。

输入JSON：
{json.dumps(payload, ensure_ascii=False)[:settings.max_source_chars]}
"""
    response = await build_client(settings).responses.parse(
        model=settings.openai_model,
        input=prompt,
        text_format=SemanticReviewResult,
        store=False,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("Semantic review returned no structured output")
    return [ReviewFinding(
        finding_id=f"LLM-{index:04d}", legal_basis=[], auto_fixable=False, source="llm",
        **finding.model_dump(),
    ) for index, finding in enumerate(parsed.findings, start=1)]
