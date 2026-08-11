from __future__ import annotations

from pydantic import BaseModel

from .base import AgentContext, compact_evidence
from ..schemas import EvidencePackage


class EvidenceMappingItem(BaseModel):
    feature: str
    evidence_ids: list[str]


class EvidencePackageOutput(BaseModel):
    embodiments: list[str]
    experimental_support: list[str]
    figure_plan: list[str]
    evidence_mapping: list[EvidenceMappingItem]
    unsupported_items: list[str]


class EmbodimentEvidenceAgent:
    name = "embodiment_evidence_agent"
    stage = "stage4_embodiment_evidence"
    label = "实施例与证据组织"

    async def run(self, context: AgentContext) -> None:
        if not context.job.solution or not context.job.paper or not context.job.understanding:
            raise ValueError("缺少技术方案结果")
        if not context.settings.offline_mode:
            result = await context.gateway.structured(
                model=context.settings.model,
                output_type=EvidencePackageOutput,
                system_prompt=(
                    "你是实施例与证据Agent。依据论文实验、算法、公式和图注组织实施例、实验支持和专利附图规划。"
                    "不得虚构数值；缺少支持的项目必须放入unsupported_items。"
                    "evidence_mapping中的每个编号必须直接支持对应技术事实，不得仅凭同章节或相近主题进行映射。"
                    "论文没有实际执行的替代实现不得写成实施例；统计数字必须能够在证据文本中逐项找到。"
                ),
                payload={
                    "solution": context.job.solution.model_dump(mode="json"),
                    "paper": context.job.paper.model_dump(mode="json"),
                    "evidence": compact_evidence(
                        context.job,
                        140,
                        keywords=(
                            "experiment", "result", "setup", "implementation", "dataset", "metric",
                            "optimizer", "learning rate", "seed", "bootstrap", "ablation", "case study",
                            "formula", "table", "figure", "appendix", "实验", "结果", "参数", "图", "表",
                        ),
                    ),
                },
            )
            context.job.evidence_package = EvidencePackage(
                embodiments=result.embodiments,
                experimental_support=result.experimental_support,
                figure_plan=result.figure_plan,
                evidence_mapping={item.feature: item.evidence_ids for item in result.evidence_mapping},
                unsupported_items=result.unsupported_items,
            )
            return
        experiment = context.job.understanding.experimental_findings
        embodiments = [
            "实施例1：按照所述步骤依次获取输入、执行核心处理并输出结果；" + "；".join(context.job.solution.method_steps[:5]),
        ]
        if context.job.paper.algorithms:
            embodiments.append("实施例2：采用论文算法环境中记载的计算过程实现核心处理模块。")
        figure_plan = ["图1为本发明方法的总体流程图。"]
        figure_plan.extend(
            f"图{index + 2}为{figure.caption}对应的专利化示意图。"
            for index, figure in enumerate(context.job.paper.figures[:6])
        )
        feature_mapping = {
            feature.name: feature.evidence_ids for feature in (context.job.invention.features if context.job.invention else [])
        }
        context.job.evidence_package = EvidencePackage(
            embodiments=embodiments,
            experimental_support=experiment[:10],
            figure_plan=figure_plan,
            evidence_mapping=feature_mapping,
            unsupported_items=[] if experiment else ["论文未提取到明确实验结论，需发明人补充验证数据。"],
        )
