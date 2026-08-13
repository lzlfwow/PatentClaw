from __future__ import annotations

import json

from pydantic import BaseModel, Field

from ..config import Settings
from ..schemas import ReviewInput, ReviewReport, TechnicalDisclosure
from .client import build_client


class RevisedDisclosure(BaseModel):
    disclosure: TechnicalDisclosure
    unresolved_finding_ids: list[str] = Field(default_factory=list)


async def revise_disclosure_online(review_input: ReviewInput, report: ReviewReport,
                                   settings: Settings) -> RevisedDisclosure:
    payload = {
        "disclosure": review_input.disclosure.model_dump(),
        "findings": [item.model_dump(mode="json") for item in report.findings],
        "evidence": [item.model_dump() for item in review_input.evidence],
    }
    prompt = f"""你是中国发明专利技术交底书改稿助手。按照审查意见优化交底书，但必须遵守以下硬约束：
1. 不得引入证据片段中不存在的技术事实、参数、部件、步骤、实验结果或效果。
2. 仅做结构重组、术语统一、专利文体转换以及有证据支持的内容补全。
3. 对无法安全修改的问题保留原文，并把 finding_id 放入 unresolved_finding_ids。
4. 不删除会缩小或改变技术方案含义的内容；不得做新颖性、创造性或侵权结论。
5. 保持字段结构完整，中文表述清楚，问题、技术特征和效果互相对应。

输入JSON：
{json.dumps(payload, ensure_ascii=False)[:settings.max_source_chars]}
"""
    response = await build_client(settings).responses.parse(
        model=settings.openai_model,
        input=prompt,
        text_format=RevisedDisclosure,
        store=False,
    )
    if response.output_parsed is None:
        raise RuntimeError("Revision agent returned no structured output")
    return response.output_parsed
