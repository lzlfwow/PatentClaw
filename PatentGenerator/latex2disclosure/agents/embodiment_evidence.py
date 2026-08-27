from __future__ import annotations

from pydantic import BaseModel

from .base import AgentContext, compact_evidence
from ..patent_figures import build_default_patent_figures, drawing_descriptions, ensure_patent_figures
from ..schemas import EvidencePackage, PatentFigure


class EvidenceMappingItem(BaseModel):
    feature: str
    evidence_ids: list[str]


class EvidencePackageOutput(BaseModel):
    embodiments: list[str]
    experimental_support: list[str]
    figure_plan: list[str]
    patent_figures: list[PatentFigure]
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
                    "实验结果必须同时支持正文中的可编辑数据表和重新绘制的中文图表；不得把数据集本身写成发明贡献。"
                    "patent_figures必须是基于solution重新组织的中文专利附图规格，不得复制论文原图、原图布局或英文图注。"
                    "优先生成总体方法流程图和系统结构示意图，共1至4幅；节点使用简洁中文专利术语，流程步骤保留S101式编号，"
                    "流程图中的步骤编号必须严格按照实际执行顺序从S101连续递增，并与solution.method_steps的相同技术动作保持一致；"
                    "系统模块使用100起的附图标记。node_id仅使用ASCII字母、数字和下划线，edge只能引用已有node_id。"
                ),
                payload={
                    "solution": context.job.solution.model_dump(mode="json"),
                    "paper": context.job.paper.model_dump(
                        mode="json", exclude={"figures": {"__all__": {"asset_path"}}}
                    ),
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
            figures = ensure_patent_figures(result.patent_figures, context.job.solution)
            context.job.evidence_package = EvidencePackage(
                embodiments=result.embodiments,
                experimental_support=result.experimental_support,
                figure_plan=drawing_descriptions(figures),
                patent_figures=figures,
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
        figures = build_default_patent_figures(context.job.solution)
        feature_mapping = {
            feature.name: feature.evidence_ids for feature in (context.job.invention.features if context.job.invention else [])
        }
        context.job.evidence_package = EvidencePackage(
            embodiments=embodiments,
            experimental_support=experiment[:10],
            figure_plan=drawing_descriptions(figures),
            patent_figures=figures,
            evidence_mapping=feature_mapping,
            unsupported_items=[] if experiment else ["论文未提取到明确实验结论，需发明人补充验证数据。"],
        )
