from __future__ import annotations

from .base import AgentContext, compact_evidence, select_section, sentences
from ..math_ooxml import normalize_disclosure_math
from ..schemas import TechnicalDisclosure


class DisclosureWriterAgent:
    name = "technical_disclosure_writer_agent"
    stage = "stage5_disclosure_drafting"
    label = "技术交底书撰写"

    async def run(self, context: AgentContext) -> None:
        if not all((context.job.paper, context.job.understanding, context.job.invention, context.job.solution, context.job.evidence_package)):
            raise ValueError("技术交底书输入不完整")
        if not context.settings.offline_mode:
            context.job.disclosure = await context.gateway.structured(
                model=context.settings.model,
                output_type=TechnicalDisclosure,
                system_prompt=(
                    "你是中国电通类技术交底书撰写Agent。按背景技术、现有技术缺陷、技术问题、详细方案、有益效果、"
                    "实施例、实验和附图说明撰写。使用客观专利语言，不写论文贡献口号，不虚构数据，并保留发明人确认项。"
                    "除必要的专业术语、模型名称和方法名称外，全文使用中文；发明名称采用技术特点加用途的命名方式且不超过25个汉字。"
                    "背景技术应使本领域技术人员无需另查文献即可理解，缺陷、技术问题、技术手段和有益效果应逐项对应；"
                    "详细方案须写清输入、处理顺序、参数关系、输出及必要的系统模块，达到可据以实施的程度。"
                    "所有技术事实、参数、模型配置和实验数值必须能够由输入证据直接支持；证据不足的内容不得写成已实施事实，"
                    "应移入inventor_confirmation_items或implementation_boundaries。alternatives仅保留论文直接披露或实际验证的方案。"
                    "terminology应统一核心术语和张量含义；system_implementation应说明系统模块、输入输出和数据流；"
                    "data_and_interfaces应说明数据对象、模型接口、存储对象和处理器执行关系。"
                    "数学变量和公式使用$...$包围的LaTeX记法；向量用\\boldsymbol{}，集合或损失等花体符号用\\mathcal{}，"
                    "上下标必须使用_{...}和^{...}，不得用普通文本下划线或尖号代替，并在terminology中逐一定义符号。"
                    "有益效果须限定为在论文披露的模型、数据集和实验配置下观察到的结果，禁止无条件推广。"
                ),
                payload={
                    "paper": context.job.paper.model_dump(mode="json"),
                    "invention": context.job.invention.model_dump(mode="json"),
                    "solution": context.job.solution.model_dump(mode="json"),
                    "evidence_package": context.job.evidence_package.model_dump(mode="json"),
                    "evidence": compact_evidence(
                        context.job,
                        140,
                        keywords=(
                            "method", "implementation", "experiment", "result", "formula", "table", "figure",
                            "layer", "inject", "decode", "training", "parameter", "方法", "实施", "实验", "公式",
                        ),
                        preferred_ids=tuple(
                            dict.fromkeys(
                                evidence_id
                                for ids in context.job.evidence_package.evidence_mapping.values()
                                for evidence_id in ids
                            )
                        ),
                    ),
                },
            )
            normalize_disclosure_math(context.job.disclosure)
            return
        paper = context.job.paper
        understanding = context.job.understanding
        invention = context.job.invention
        solution = context.job.solution
        package = context.job.evidence_package
        background_text = select_section(context.job, ("introduction", "background", "related", "引言", "背景", "相关工作"))
        background = sentences(background_text, 20)[:5] or [understanding.research_objective]
        effects = [feature.technical_effect for feature in invention.features if feature.technical_effect]
        context.job.disclosure = TechnicalDisclosure(
            invention_title=invention.proposed_title,
            technical_field=understanding.technical_field,
            background=background,
            prior_art_defects=[f"现有技术在{problem}方面仍存在不足。" for problem in invention.technical_problem],
            technical_problem=invention.technical_problem,
            overall_solution=invention.inventive_concept,
            detailed_steps=solution.method_steps,
            key_innovations=[f"{feature.name}：{feature.description}" for feature in invention.features],
            beneficial_effects=list(dict.fromkeys(effects))[:8],
            embodiments=package.embodiments,
            experimental_evidence=package.experimental_support,
            drawing_descriptions=package.figure_plan,
            terminology=[
                "输入数据：进入所述计算机实现方法并由第一处理步骤读取的数据对象。",
                "中间表示：由模型或算法步骤生成并传递至后续处理步骤的数值表示。",
                "输出结果：执行所述技术步骤后产生的模型输出或评价结果。",
            ],
            system_implementation=solution.components,
            data_and_interfaces=solution.data_flow,
            implementation_boundaries=package.unsupported_items,
            alternatives=solution.alternative_paths,
            inventor_confirmation_items=invention.inventor_questions + package.unsupported_items,
        )
        normalize_disclosure_math(context.job.disclosure)
