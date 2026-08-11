from __future__ import annotations

from .base import AgentContext, compact_evidence
from ..schemas import TechnicalSolution


class TechnicalSolutionAgent:
    name = "technical_solution_agent"
    stage = "stage3_technical_solution"
    label = "技术方案重构"

    async def run(self, context: AgentContext) -> None:
        if not context.job.invention or not context.job.understanding:
            raise ValueError("缺少发明挖掘结果")
        if not context.settings.offline_mode:
            context.job.solution = await context.gateway.structured(
                model=context.settings.model,
                output_type=TechnicalSolution,
                system_prompt=(
                    "你是技术方案重构Agent。把论文叙述改写为可实施的专利技术链条，明确输入、步骤、数据流、参数关系和输出。"
                    "步骤使用S101开始的连续编号；仅使用证据支持的内容。"
                    "不得自行补造模型挂接位置、张量形状、映射算法、损失函数、参数范围或系统接口。"
                    "缺少直接证据的实现细节不得进入method_steps、components或alternative_paths；仅保留在参数约束或待确认语义中。"
                ),
                payload={
                    "understanding": context.job.understanding.model_dump(mode="json"),
                    "invention": context.job.invention.model_dump(mode="json"),
                    "evidence": compact_evidence(
                        context.job,
                        100,
                        keywords=(
                            "method", "formulation", "implementation", "algorithm", "equation", "formula",
                            "layer", "inject", "decode", "training", "parameter", "constraint",
                            "方法", "公式", "步骤", "参数", "实施",
                        ),
                        preferred_ids=tuple(
                            dict.fromkeys(
                                context.job.understanding.evidence_ids
                                + [evidence_id for feature in context.job.invention.features for evidence_id in feature.evidence_ids]
                            )
                        ),
                    ),
                },
            )
            return
        understanding = context.job.understanding
        raw_steps = understanding.workflow_steps or [context.job.invention.inventive_concept]
        steps = [f"S{100 + index}：{step}" for index, step in enumerate(raw_steps[:10], start=1)]
        components = [f"{feature.name}模块：{feature.description}" for feature in context.job.invention.features[:6]]
        context.job.solution = TechnicalSolution(
            system_boundary="由论文披露的输入获取、核心处理和结果输出环节构成计算机实现的处理系统。",
            components=components,
            method_steps=steps,
            data_flow=[f"步骤{index}的处理结果作为步骤{index + 1}的输入。" for index in range(1, max(1, len(steps) - 1))],
            parameters_and_constraints=[item for item in context.job.paper.equations[:8]] if context.job.paper else [],
            alternative_paths=context.job.invention.alternatives,
            evidence_ids=list(dict.fromkeys(understanding.evidence_ids)),
        )
