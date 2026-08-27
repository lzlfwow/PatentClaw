from __future__ import annotations

from .base import AgentContext, compact_evidence
from ..math_ooxml import contains_unmarked_math
from ..schemas import ReviewFinding, ReviewReport


class IndependentReviewAgent:
    name = "independent_review_agent"
    stage = "stage6_independent_review"
    label = "独立质量审查"

    async def run(self, context: AgentContext) -> None:
        if not context.job.disclosure:
            raise ValueError("缺少技术交底书草案")
        if not context.settings.offline_mode:
            mapped_ids = tuple(
                dict.fromkeys(
                    evidence_id
                    for ids in (context.job.evidence_package.evidence_mapping.values() if context.job.evidence_package else [])
                    for evidence_id in ids
                )
            )
            context.job.review = await context.gateway.structured(
                model=context.settings.review_model,
                output_type=ReviewReport,
                system_prompt=(
                    "你是独立专利质量审查Agent，不参与初稿撰写。检查标题、章节完整性、术语一致性、技术链条、"
                    "证据支持、实施充分性和虚构风险。还要检查正文是否以中文为主，背景是否自足，缺陷、技术问题、"
                    "技术手段与有益效果是否对应，实验是否包含可制表和制图的数据，以及数学表达是否使用$...$包围的"
                    "规范LaTeX、向量粗体、花体集合、真实上下标和逐项符号定义。评分应保守，给出可执行整改意见。"
                ),
                payload={
                    "disclosure": context.job.disclosure.model_dump(mode="json"),
                    "evidence_mapping": context.job.evidence_package.evidence_mapping if context.job.evidence_package else {},
                    "evidence": compact_evidence(
                        context.job,
                        160,
                        keywords=(
                            "method", "implementation", "experiment", "result", "setup", "appendix",
                            "formula", "table", "figure", "seed", "bootstrap", "ablation", "case study",
                            "layer", "inject", "decode", "training", "parameter", "limitation",
                            "方法", "实施", "实验", "结果", "公式", "表格", "附图",
                        ),
                        preferred_ids=mapped_ids,
                    ),
                },
            )
            return
        disclosure = context.job.disclosure
        findings: list[ReviewFinding] = []
        score = 100
        if len(disclosure.invention_title) > 25:
            findings.append(ReviewFinding(
                severity="major", code="TITLE_LENGTH", message="发明名称超过25个汉字。", remediation="压缩为技术对象与核心手段。"
            ))
            score -= 12
        required = {
            "背景技术": disclosure.background,
            "技术方案": disclosure.detailed_steps,
            "创新点": disclosure.key_innovations,
            "实施例": disclosure.embodiments,
            "附图说明": disclosure.drawing_descriptions,
        }
        for label, value in required.items():
            if not value:
                findings.append(ReviewFinding(
                    severity="major", code="MISSING_SECTION", message=f"缺少{label}内容。", remediation=f"补充{label}及其证据来源。"
                ))
                score -= 10
        missing_support = context.job.evidence_package.unsupported_items if context.job.evidence_package else []
        if missing_support:
            findings.append(ReviewFinding(
                severity="minor", code="INVENTOR_CONFIRMATION", message="存在需要发明人确认的无支持项目。", remediation="提交发明人访谈并补充原始记录。"
            ))
            score -= 6
        if not disclosure.experimental_evidence:
            findings.append(ReviewFinding(
                severity="minor", code="NO_EXPERIMENT", message="未提取到实验依据。", remediation="从论文结果章节补充可复核实验数据。"
            ))
            score -= 6
        all_text = "\n".join(
            [
                disclosure.overall_solution,
                *disclosure.detailed_steps,
                *disclosure.embodiments,
                *disclosure.terminology,
                *disclosure.data_and_interfaces,
            ]
        )
        if contains_unmarked_math(all_text):
            findings.append(ReviewFinding(
                severity="major",
                code="MATH_NOTATION",
                message="存在使用普通下划线或尖号书写的数学变量。",
                remediation="使用$...$ LaTeX标记，并统一向量、集合、上下标和符号定义。",
            ))
            score -= 10
        if context.job.evidence_package and not context.job.evidence_package.patent_figures:
            findings.append(ReviewFinding(
                severity="major",
                code="NO_PATENT_FIGURE",
                message="未生成可核查的专利附图规格。",
                remediation="根据技术步骤重绘中文流程图或系统结构图并提供可编辑源文件。",
            ))
            score -= 10
        context.job.review = ReviewReport(
            score=max(0, score),
            passed=score >= 80 and not any(item.severity == "critical" for item in findings),
            findings=findings,
            missing_support=missing_support,
            human_review_checklist=[
                "确认论文、预印本、代码和答辩材料的公开日期。",
                "由发明人确认必要技术特征与替代实施方案。",
                "由专利代理师执行正式专利检索并确定权利要求范围。",
            ],
        )
