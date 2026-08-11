from __future__ import annotations

from .base import AgentContext, compact_evidence
from ..schemas import InventionDisclosure, TechnicalFeature


def _patent_title(title: str) -> str:
    cleaned = title.strip().strip(".。")
    if cleaned.startswith("一种"):
        return cleaned[:25]
    lowered = cleaned.lower()
    if all(keyword in lowered for keyword in ("representation", "exploration")):
        return "一种基于自适应表征探索的多样化生成方法"
    if cleaned.isascii():
        return "一种基于论文技术方案的计算机处理方法"
    return f"一种{cleaned}方法"[:25]


class InventionMiningAgent:
    name = "invention_mining_agent"
    stage = "stage2_invention_mining"
    label = "发明点挖掘"

    async def run(self, context: AgentContext) -> None:
        if not context.job.paper or not context.job.understanding:
            raise ValueError("缺少论文理解结果")
        if not context.settings.offline_mode:
            context.job.invention = await context.gateway.structured(
                model=context.settings.model,
                output_type=InventionDisclosure,
                system_prompt=(
                    "你是发明挖掘Agent。按照技术问题-技术手段-技术效果识别可专利化特征。"
                    "区分必要特征与优选特征，标题不超过25个汉字，严禁把论文贡献口号直接当作技术特征。"
                    "每个技术特征必须列出直接支持其实现的evidence_ids。论文未披露实现参数、训练方法或实验结果的扩展设想，"
                    "不得写入features或alternatives，应改写为inventor_questions。不得把建议性方案描述为已经验证。"
                ),
                payload={
                    "paper_understanding": context.job.understanding.model_dump(mode="json"),
                    "evidence": compact_evidence(
                        context.job,
                        80,
                        keywords=(
                            "method", "formulation", "difference", "novel", "improve", "outperform",
                            "injection", "adaptation", "transfer", "ablation", "方法", "创新", "效果",
                        ),
                        preferred_ids=tuple(context.job.understanding.evidence_ids),
                    ),
                },
            )
            return
        understanding = context.job.understanding
        steps = understanding.workflow_steps or [understanding.method_summary]
        evidence_ids = understanding.evidence_ids
        features = [
            TechnicalFeature(
                name=f"技术特征{index}",
                description=step,
                solved_problem=understanding.research_objective,
                technical_effect=(understanding.experimental_findings[index - 1] if index <= len(understanding.experimental_findings) else "实现论文所述处理结果"),
                essential=index <= min(4, len(steps)),
                evidence_ids=evidence_ids[max(0, index - 1) : index + 1],
            )
            for index, step in enumerate(steps[:8], start=1)
        ]
        context.job.invention = InventionDisclosure(
            proposed_title=_patent_title(context.job.paper.title),
            technical_problem=[understanding.research_objective],
            inventive_concept=understanding.method_summary,
            features=features,
            alternatives=["对关键模型、距离度量、筛选策略或数据表示采用功能等同的替代实现。"],
            inventor_questions=["请确认论文公开日前是否存在未公开的替代方案或关键参数范围。"],
        )
