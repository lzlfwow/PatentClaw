from __future__ import annotations

from .base import AgentContext, compact_evidence, select_section, sentences
from ..schemas import PaperUnderstanding


class PaperUnderstandingAgent:
    name = "paper_understanding_agent"
    stage = "stage1_paper_understanding"
    label = "论文技术理解"

    async def run(self, context: AgentContext) -> None:
        paper = context.job.paper
        if paper is None:
            raise ValueError("论文尚未解析")
        if not context.settings.offline_mode:
            context.job.understanding = await context.gateway.structured(
                model=context.settings.model,
                output_type=PaperUnderstanding,
                system_prompt=(
                    "你是论文技术理解Agent。只依据输入的LaTeX论文与证据提取研究对象、输入、处理步骤、输出和实验结论。"
                    "不得推测论文未披露的参数；所有关键结论列出证据编号。"
                ),
                payload={
                    "paper": paper.model_dump(mode="json"),
                    "evidence": compact_evidence(
                        context.job,
                        100,
                        keywords=(
                            "method", "methodology", "formulation", "algorithm", "implementation",
                            "experiment", "result", "evaluation", "ablation", "appendix",
                            "formula", "table", "figure", "方法", "实验", "结果", "公式", "表格",
                        ),
                    ),
                },
            )
            return
        method_text = select_section(context.job, ("method", "approach", "framework", "methodology", "方法", "模型"))
        result_text = select_section(context.job, ("experiment", "result", "evaluation", "实验", "结果"))
        intro_text = select_section(context.job, ("introduction", "background", "引言", "背景"))
        method_sentences = sentences(method_text or paper.abstract or paper.plain_text)
        result_sentences = sentences(result_text)
        evidence_ids = [item.evidence_id for item in context.job.evidence[:12]]
        context.job.understanding = PaperUnderstanding(
            technical_field=(sentences(intro_text or paper.abstract, 10) or ["论文所述计算机实现技术领域"])[0][:180],
            research_objective=(sentences(paper.abstract or intro_text, 10) or [f"围绕{paper.title}解决相关技术问题"])[0][:240],
            method_summary="；".join(method_sentences[:3]) or f"论文提出了{paper.title}所述技术方案。",
            inputs=[item for item in method_sentences if any(key in item.lower() for key in ("input", "given", "输入", "数据"))][:4],
            workflow_steps=method_sentences[:8],
            outputs=[item for item in method_sentences if any(key in item.lower() for key in ("output", "generate", "predict", "输出", "生成"))][:4],
            experimental_findings=result_sentences[:8],
            evidence_ids=evidence_ids,
        )
