from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ..checklist import CHECKS_BY_ID, SEMANTIC_CHECKS
from ..config import Settings
from ..schemas import (
    ChecklistEvaluation,
    CheckStatus,
    ReviewFinding,
    ReviewInput,
)
from .client import build_client
from .context import semantic_payload, serialized_payload


class SemanticCheckResult(BaseModel):
    check_id: str
    status: CheckStatus
    reason: str
    target_section: str = ""
    target_path: str = ""
    original_text: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_revision: str = ""
    requires_inventor_confirmation: bool = False
    confidence: float = Field(default=0.8, ge=0, le=1)


class SemanticChecklistResult(BaseModel):
    checks: list[SemanticCheckResult]

    @model_validator(mode="after")
    def complete_fixed_checklist(self) -> "SemanticChecklistResult":
        expected = {item.check_id for item in SEMANTIC_CHECKS}
        received = [item.check_id for item in self.checks]
        unknown = set(received) - expected
        missing = expected - set(received)
        if unknown or missing or len(received) != len(set(received)):
            raise ValueError(
                f"Semantic checklist must contain each fixed check exactly once; "
                f"missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        invalid = [
            item.check_id for item in self.checks
            if item.status == CheckStatus.not_assessed
        ]
        if invalid:
            raise ValueError(f"Online semantic checks cannot be not_assessed: {invalid}")
        return self


class SemanticReviewOutput(BaseModel):
    evaluations: list[ChecklistEvaluation]
    findings: list[ReviewFinding]


async def semantic_review_online(
    review_input: ReviewInput,
    settings: Settings,
) -> SemanticReviewOutput:
    payload = semantic_payload(review_input, settings.max_source_chars)
    checklist_text = "\n".join(
        f"- {item.check_id} [{item.dimension.value}] {item.title}：{item.criterion}"
        for item in SEMANTIC_CHECKS
    )
    prompt = f"""你是中国发明专利技术交底书的固定检查表审查器，不得自由增加、删除、合并或改名检查项。
你必须对下列每个check_id恰好返回一次判定：
{checklist_text}

状态只能使用：
- pass：证据足以确认该项通过；
- fail：存在明确问题；
- needs_human_review：当前材料不足以确认通过，且该不确定性可能影响申请质量；
- not_applicable：该项客观上不适用于本交底书。

约束：
1. fail和needs_human_review必须说明reason、target_path、证据编号和可执行修改建议；无证据时明确说明材料缺口。
2. pass不得为了凑数虚构证据；not_applicable必须说明不适用原因。
3. target_path必须是交底书顶层字段名，若影响多处选择根因所在的主要字段。
4. 不进行新颖性、创造性、授权概率或侵权结论。
5. 只判断固定检查项，不输出维度、严重程度或额外问题。

输入JSON：
{serialized_payload(payload)}
"""
    response = await build_client(settings).responses.parse(
        model=settings.openai_model,
        input=prompt,
        text_format=SemanticChecklistResult,
        store=False,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("Semantic review returned no structured output")

    evaluations = []
    findings = []
    for result in parsed.checks:
        spec = CHECKS_BY_ID[result.check_id]
        evaluations.append(ChecklistEvaluation(
            check_id=spec.check_id,
            dimension=spec.dimension,
            title=spec.title,
            severity=spec.severity,
            status=result.status,
            evaluator="llm",
            reason=result.reason,
            evidence_ids=result.evidence_ids,
        ))
        if result.status not in (CheckStatus.failed, CheckStatus.needs_human_review):
            continue
        findings.append(ReviewFinding(
            finding_id=f"C-{spec.check_id}",
            check_id=spec.check_id,
            dimension=spec.dimension,
            severity=spec.severity,
            code=spec.check_id,
            target_section=result.target_section or spec.title,
            target_path=result.target_path or "overall_solution",
            original_text=result.original_text,
            issue=result.reason or f"固定检查项未通过：{spec.title}",
            risk=spec.criterion,
            reason=result.reason,
            evidence_ids=result.evidence_ids,
            suggested_revision=result.suggested_revision,
            requires_inventor_confirmation=result.requires_inventor_confirmation,
            confidence=result.confidence,
            source="llm",
        ))
    return SemanticReviewOutput(evaluations=evaluations, findings=findings)
