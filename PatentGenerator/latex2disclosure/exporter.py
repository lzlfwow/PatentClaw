from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor

from .schemas import PipelineJob


NAVY = RGBColor(31, 77, 120)
MUTED = RGBColor(95, 103, 112)
BLACK = RGBColor(0, 0, 0)
CN_FONT = "Microsoft YaHei"


def _join(items: list[str], fallback: str = "待补充") -> str:
    return "\n".join(items) if items else fallback


def markdown(job: PipelineJob) -> str:
    disclosure = job.disclosure
    if disclosure is None:
        raise ValueError("技术交底书尚未生成")
    lines = [
        f"# {disclosure.invention_title}",
        "",
        f"> 项目编号：{job.job_id}｜来源：{job.input_name}",
        "",
        "## 1. 技术领域",
        "",
        disclosure.technical_field,
        "",
        "## 2. 背景技术",
        "",
        *[f"- {item}" for item in disclosure.background],
        "",
        "## 3. 现有技术缺陷与技术问题",
        "",
        *[f"- {item}" for item in disclosure.prior_art_defects + disclosure.technical_problem],
        "",
        "## 4. 技术方案",
        "",
        disclosure.overall_solution,
        "",
        *[f"{index}. {item}" for index, item in enumerate(disclosure.detailed_steps, start=1)],
        "",
        "## 5. 关键创新点",
        "",
        *[f"- {item}" for item in disclosure.key_innovations],
        "",
        "## 6. 有益效果",
        "",
        *[f"- {item}" for item in disclosure.beneficial_effects],
        "",
        "## 7. 具体实施方式",
        "",
        *[f"### 实施例{index}\n\n{item}" for index, item in enumerate(disclosure.embodiments, start=1)],
        "",
        "## 8. 实验依据",
        "",
        *[f"- {item}" for item in disclosure.experimental_evidence],
        "",
        "## 9. 附图说明",
        "",
        *[f"- {item}" for item in disclosure.drawing_descriptions],
        "",
        "## 10. 系统实现",
        "",
        *[f"- {item}" for item in disclosure.system_implementation],
        "",
        "## 11. 数据与接口",
        "",
        *[f"- {item}" for item in disclosure.data_and_interfaces],
        "",
        "## 12. 术语与符号",
        "",
        *[f"- {item}" for item in disclosure.terminology],
        "",
        "## 13. 实施边界",
        "",
        *[f"- {item}" for item in disclosure.implementation_boundaries],
        "",
        "## 14. 替代实施方式",
        "",
        *[f"- {item}" for item in disclosure.alternatives],
        "",
        "## 15. 发明人确认事项",
        "",
        *[f"- {item}" for item in disclosure.inventor_confirmation_items],
    ]
    lines.extend(["", "---", "本文件由Agent辅助生成，仅供发明人和专利代理师审阅，不构成法律意见。"])
    return "\n".join(lines)


def _set_font(run, size: float, bold: bool = False, color: RGBColor = BLACK) -> None:
    run.font.name = CN_FONT
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), CN_FONT)
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Calibri")
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Calibri")
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color


def _configure_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = CN_FONT
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.1
    for name, size, before, after, color in (
        ("Heading 1", 16, 16, 8, NAVY),
        ("Heading 2", 13, 12, 6, NAVY),
        ("Heading 3", 12, 8, 4, RGBColor(31, 77, 120)),
    ):
        style = document.styles[name]
        style.font.name = CN_FONT
        style._element.rPr.rFonts.set(qn("w:eastAsia"), CN_FONT)
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)


def _page_field(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("第 ")
    _set_font(run, 9, color=MUTED)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    run._r.addnext(field)
    tail = paragraph.add_run(" 页")
    _set_font(tail, 9, color=MUTED)


def _add_list(document: Document, items: list[str], style: str) -> None:
    if not items:
        document.add_paragraph("待补充并由发明人确认。")
        return
    for item in items:
        paragraph = document.add_paragraph(style=style)
        paragraph.paragraph_format.space_after = Pt(6)
        paragraph.paragraph_format.line_spacing = 1.1
        run = paragraph.add_run(item)
        _set_font(run, 11)


def _asset_image(asset_path: Path, cache_dir: Path, index: int) -> Path | None:
    suffix = asset_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        return asset_path
    if suffix != ".pdf":
        return None
    output = cache_dir / f"figure-{index}.png"
    try:
        import fitz

        pdf = fitz.open(asset_path)
        if not pdf.page_count:
            return None
        pixmap = pdf[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        pixmap.save(output)
        pdf.close()
        return output
    except (ImportError, OSError, RuntimeError):
        pdftoppm = shutil.which("pdftoppm")
        if not pdftoppm:
            return None
        prefix = cache_dir / f"figure-{index}"
        completed = subprocess.run(
            [pdftoppm, "-f", "1", "-singlefile", "-png", "-r", "180", str(asset_path), str(prefix)],
            capture_output=True,
            check=False,
        )
        return output if completed.returncode == 0 and output.is_file() else None


def _add_source_figures(document: Document, job: PipelineJob, cache_dir: Path) -> int:
    if not job.paper:
        return 0
    inserted = 0
    for index, figure in enumerate(job.paper.figures, start=1):
        if not figure.asset_path:
            continue
        asset = Path(figure.asset_path)
        if not asset.is_file():
            continue
        image_path = _asset_image(asset, cache_dir, index)
        if image_path is None:
            continue
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        run.add_picture(str(image_path), width=Inches(6.15))
        caption = document.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.paragraph_format.keep_with_next = True
        _set_font(caption.add_run(f"图{index}  {figure.caption}"), 9.5, color=MUTED)
        inserted += 1
    return inserted


def docx(job: PipelineJob, output_path: Path) -> None:
    disclosure = job.disclosure
    if disclosure is None:
        raise ValueError("技术交底书尚未生成")
    document = Document()
    section = document.sections[0]
    # Chinese technical disclosures are normally exchanged on ISO A4 paper.
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    _configure_styles(document)

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_run = header.add_run("技术交底书")
    _set_font(header_run, 9, color=MUTED)
    _page_field(section.footer.paragraphs[0])

    title = document.add_paragraph()
    title.paragraph_format.space_before = Pt(12)
    title.paragraph_format.space_after = Pt(4)
    title_run = title.add_run("技术交底书")
    _set_font(title_run, 23, bold=True)
    subtitle = document.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(14)
    subtitle_run = subtitle.add_run(disclosure.invention_title)
    _set_font(subtitle_run, 14, bold=True, color=NAVY)
    for label, value in (
        ("项目编号", job.job_id),
        ("来源文件", job.input_name),
        ("生成状态", "待发明人及专利代理师复核"),
        ("发明人", "待填写"),
        ("联系人", "待填写"),
        ("完成日期", "待填写"),
    ):
        p = document.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        label_run = p.add_run(f"{label}：")
        _set_font(label_run, 10.5, bold=True)
        _set_font(p.add_run(value), 10.5)

    notice = document.add_paragraph()
    notice.paragraph_format.space_before = Pt(5)
    notice.paragraph_format.space_after = Pt(10)
    notice_run = notice.add_run("本文件由Agent辅助生成，仅用于技术整理与专业审阅，不构成法律意见。")
    _set_font(notice_run, 8.5, color=MUTED)

    sections: list[tuple[str, str | list[str], str]] = [
        ("1. 技术领域", disclosure.technical_field, "prose"),
        ("2. 背景技术", disclosure.background, "bullet"),
        ("3. 现有技术缺陷", disclosure.prior_art_defects, "bullet"),
        ("4. 本发明解决的技术问题", disclosure.technical_problem, "bullet"),
        ("5. 总体技术构思", disclosure.overall_solution, "prose"),
        ("6. 详细技术方案", disclosure.detailed_steps, "number"),
        ("7. 关键创新点", disclosure.key_innovations, "bullet"),
        ("8. 有益效果", disclosure.beneficial_effects, "bullet"),
        ("9. 具体实施方式", disclosure.embodiments, "bullet"),
        ("10. 实验依据", disclosure.experimental_evidence, "bullet"),
        ("11. 附图说明", disclosure.drawing_descriptions, "bullet"),
        ("12. 系统实现", disclosure.system_implementation, "bullet"),
        ("13. 数据与接口", disclosure.data_and_interfaces, "bullet"),
        ("14. 术语与符号", disclosure.terminology, "bullet"),
        ("15. 实施边界", disclosure.implementation_boundaries, "bullet"),
        ("16. 替代实施方式", disclosure.alternatives, "bullet"),
        ("17. 发明人确认事项", disclosure.inventor_confirmation_items, "bullet"),
    ]
    cache_dir = Path(tempfile.mkdtemp(prefix="l2d-figures-"))
    try:
        for heading, content, form in sections:
            document.add_heading(heading, level=1)
            if isinstance(content, str):
                paragraph = document.add_paragraph(content or "待补充并由发明人确认。")
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            elif form == "number":
                _add_list(document, content, "List Number")
            else:
                _add_list(document, content, "List Bullet")
            if heading.startswith("11."):
                _add_source_figures(document, job, cache_dir)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(output_path)
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


def export_job(job: PipelineJob, data_dir: Path) -> dict[str, str]:
    root = data_dir / job.job_id / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    markdown_path = root / "technical_disclosure.md"
    docx_path = root / "technical_disclosure.docx"
    json_path = root / "job.json"
    artifacts = {
        "markdown": str(markdown_path.resolve()),
        "docx": str(docx_path.resolve()),
        "json": str(json_path.resolve()),
    }
    job.artifacts = artifacts
    markdown_path.write_text(markdown(job), encoding="utf-8")
    docx(job, docx_path)
    json_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return artifacts
