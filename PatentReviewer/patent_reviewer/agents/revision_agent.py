from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..config import Settings
from ..schemas import (
    ChangeRecord,
    ChecklistEvaluation,
    IssueRevisionAttempt,
    ReviewFinding,
    ReviewInput,
    TechnicalDisclosure,
)
from .client import build_client
from .context import issue_revision_payload, serialized_payload


DisclosureField = Literal[
    "invention_title", "technical_field", "background", "prior_art_defects",
    "technical_problem", "overall_solution", "detailed_steps", "key_innovations",
    "beneficial_effects", "embodiments", "experimental_evidence", "drawing_descriptions",
    "terminology", "system_implementation", "data_and_interfaces",
    "implementation_boundaries", "alternatives", "inventor_confirmation_items",
]


class DisclosureFragmentPatch(BaseModel):
    target_path: DisclosureField
    original_fragment: str = Field(min_length=1)
    replacement_fragment: str
    finding_ids: list[str] = Field(min_length=1)


class IssueRevisionDecision(BaseModel):
    check_id: str
    outcome: Literal["modified", "blocked", "no_change"]
    patches: list[DisclosureFragmentPatch] = Field(default_factory=list)
    reason: str = ""
    requested_materials: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def patches_match_outcome(self) -> "IssueRevisionDecision":
        if self.outcome == "modified" and not self.patches:
            raise ValueError("modified outcome requires at least one fragment patch")
        if self.outcome != "modified" and self.patches:
            raise ValueError("blocked/no_change outcome cannot contain patches")
        if self.outcome == "blocked" and not self.reason:
            raise ValueError("blocked outcome requires a reason")
        return self


class IssueRevisionResult(BaseModel):
    disclosure: TechnicalDisclosure
    attempt: IssueRevisionAttempt


async def revise_issue_online(
    review_input: ReviewInput,
    evaluation: ChecklistEvaluation,
    findings: list[ReviewFinding],
    settings: Settings,
    round_number: int,
) -> IssueRevisionResult:
    """Run one isolated revision agent for exactly one fixed checklist item."""
    finding_ids = list(dict.fromkeys(item.finding_id for item in findings))
    allowed_paths = list(dict.fromkeys(
        item.target_path for item in findings
        if item.target_path in TechnicalDisclosure.model_fields
    ))
    payload = issue_revision_payload(
        review_input,
        evaluation,
        findings,
        allowed_paths,
        settings.max_source_chars,
    )
    prompt = f"""你是中国发明专利技术交底书的单问题改稿Agent。本次只能处理固定检查项 {evaluation.check_id}，不得顺便处理其他问题。

硬约束：
1. 只能修改 allowed_target_paths 中的字段；read_only_disclosure 只用于理解上下文，禁止修改其他字段。
2. patches 必须使用原文片段精确替换。original_fragment 必须在对应字段中恰好出现一次，并尽量选择能定位问题的最小连续片段；禁止返回整个交底书。
3. 每个 patch 的 finding_ids 只能引用本次 findings 中的 finding_id，不得引用其他问题。
4. 不得引入证据中不存在的技术事实、参数、部件、步骤、实验结果或效果。
5. 应优先进行有证据的补充、边界明确化、术语修正，以及删除或收窄非核心且无证据的扩写；不得通过删除核心技术方案来规避充分公开问题。
6. 若解决问题必须补充当前证据中不存在的事实，不得猜测。返回 blocked，并在 requested_materials 中逐项写明需要发明人补充的材料。
7. 若可安全修改，必须返回 modified 和局部 patches；仅当现有文本事实上已经满足该检查项时返回 no_change。
8. check_id 必须原样返回 {evaluation.check_id}。不得作新颖性、创造性、授权概率或侵权结论。

输入JSON：
{serialized_payload(payload)}
"""
    response = await build_client(settings).responses.parse(
        model=settings.openai_model,
        input=prompt,
        text_format=IssueRevisionDecision,
        store=False,
    )
    decision = response.output_parsed
    if decision is None:
        raise RuntimeError(f"Revision agent for {evaluation.check_id} returned no structured output")

    base_attempt = {
        "round_number": round_number,
        "check_id": evaluation.check_id,
        "finding_ids": finding_ids,
        "allowed_target_paths": allowed_paths,
        "reason": decision.reason,
        "requested_materials": decision.requested_materials,
        "evidence_ids": decision.evidence_ids,
    }
    try:
        revised, changes = apply_issue_patches(
            review_input.disclosure,
            decision,
            expected_check_id=evaluation.check_id,
            allowed_target_paths=allowed_paths,
            allowed_finding_ids=finding_ids,
            round_number=round_number,
        )
    except ValueError as exc:
        return IssueRevisionResult(
            disclosure=review_input.disclosure,
            attempt=IssueRevisionAttempt(**{
                **base_attempt,
                "outcome": "rejected",
                "reason": str(exc),
            }),
        )

    return IssueRevisionResult(
        disclosure=revised,
        attempt=IssueRevisionAttempt(
            **base_attempt,
            outcome=decision.outcome,
            changes=changes,
        ),
    )


def apply_issue_patches(
    disclosure: TechnicalDisclosure,
    decision: IssueRevisionDecision,
    *,
    expected_check_id: str,
    allowed_target_paths: list[str],
    allowed_finding_ids: list[str],
    round_number: int,
) -> tuple[TechnicalDisclosure, list[ChangeRecord]]:
    """Validate and apply only exact, issue-scoped fragment replacements."""
    if decision.check_id != expected_check_id:
        raise ValueError(
            f"Revision agent returned check_id {decision.check_id!r}; expected {expected_check_id!r}"
        )
    if decision.outcome != "modified":
        return disclosure, []

    allowed_paths = set(allowed_target_paths)
    allowed_ids = set(allowed_finding_ids)
    data = disclosure.model_dump()
    changes: list[ChangeRecord] = []
    for index, patch in enumerate(decision.patches, start=1):
        if patch.target_path not in allowed_paths:
            raise ValueError(
                f"Patch target {patch.target_path!r} is outside this issue's allowed fields"
            )
        if not set(patch.finding_ids) <= allowed_ids:
            raise ValueError("Patch references finding_ids from another checklist issue")
        if patch.original_fragment == patch.replacement_fragment:
            raise ValueError("Fragment patch does not change the text")

        data[patch.target_path] = _replace_unique_fragment(
            data[patch.target_path],
            patch.original_fragment,
            patch.replacement_fragment,
        )
        changes.append(ChangeRecord(
            action_id=f"R{round_number}-{expected_check_id}-{index:03d}",
            target_path=patch.target_path,
            before=patch.original_fragment,
            after=patch.replacement_fragment,
            finding_ids=patch.finding_ids,
        ))
    return TechnicalDisclosure.model_validate(data), changes


def _replace_unique_fragment(
    value: str | list[str],
    original_fragment: str,
    replacement_fragment: str,
) -> str | list[str]:
    if isinstance(value, str):
        if value.count(original_fragment) != 1:
            raise ValueError("original_fragment must occur exactly once in target field")
        return value.replace(original_fragment, replacement_fragment, 1)

    matches = [index for index, item in enumerate(value) if original_fragment in item]
    occurrences = sum(item.count(original_fragment) for item in value)
    if occurrences != 1 or len(matches) != 1:
        raise ValueError("original_fragment must occur exactly once in target field")
    index = matches[0]
    revised = list(value)
    revised[index] = revised[index].replace(original_fragment, replacement_fragment, 1)
    return [item for item in revised if item.strip()]
