from __future__ import annotations

from ..constants import DISCLOSURE_SECTION_LABELS
from ..schemas import PatentFigureAsset, ReviewReport, TechnicalDisclosure


def disclosure_markdown(
    disclosure: TechnicalDisclosure,
    figures: list[PatentFigureAsset] | None = None,
) -> str:
    lines = [f"# {disclosure.invention_title or '技术交底书'}", ""]
    for field, label in DISCLOSURE_SECTION_LABELS.items():
        if field == "invention_title":
            continue
        value = getattr(disclosure, field)
        lines.extend([f"## {label}", ""])
        if isinstance(value, list):
            lines.extend([f"{index}. {item}" for index, item in enumerate(value, start=1)] or ["（待补充）"])
        else:
            lines.append(value or "（待补充）")
        lines.append("")
    if figures:
        lines.extend(["## 专利附图", ""])
        for figure in figures:
            image_name = f"figures/figure-{figure.figure_no}.png"
            lines.extend([
                f"![图{figure.figure_no} {figure.title}]({image_name})",
                f"图{figure.figure_no}　{figure.title}",
                "",
            ])
        lines.append("> 附图继承自前一步生成器的结构化专利附图，并嵌入最终交底书；未复用论文原图。")
    return "\n".join(lines)


def review_markdown(report: ReviewReport, title: str) -> str:
    lines = [f"# {title}", "", f"- 总分：{report.score}/100", f"- 结论：{'通过固定检查表基线' if report.passed else '存在待处理问题'}",
             f"- 法规基线：{report.legal_baseline}", "", "## 固定检查表", "",
             "| ID | 维度 | 检查项 | 执行器 | 严重程度 | 状态 | 终审变化 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in report.checklist:
        lines.append(
            f"| `{item.check_id}` | {item.dimension.value} | {item.title} | "
            f"{item.evaluator} | {item.severity.value} | {item.status.value} | "
            f"{item.resolution or '-'} |"
        )
    lines.extend(["", "## 审查意见", ""])
    if not report.findings:
        lines.append("未发现规则可识别问题。")
    for index, item in enumerate(report.findings, start=1):
        lines.extend([
            f"### {index}. [{item.severity.value}] {item.issue}", "",
            f"- 编码：`{item.code}`",
            f"- 检查项：`{item.check_id}`",
            f"- 维度：{item.dimension.value}",
            f"- 位置：`{item.target_path}`",
            f"- 风险：{item.risk}",
            f"- 建议：{item.suggested_revision or '人工核查'}",
            f"- 证据：{', '.join(item.evidence_ids) or '未绑定'}",
            f"- 发明人确认：{'是' if item.requires_inventor_confirmation else '否'}",
        ])
        if item.legal_basis:
            lines.append(f"- 依据：{'；'.join(item.legal_basis)}")
        lines.append("")
    lines.extend(["## 人工终检清单", ""] + [f"- {item}" for item in report.human_review_checklist])
    lines.extend(["", "## 使用边界", ""] + [f"- {item}" for item in report.limitations])
    return "\n".join(lines) + "\n"
