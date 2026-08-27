from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .schemas import PatentFigure, PatentFigureEdge, PatentFigureNode, TechnicalSolution


CANVAS_WIDTH = 1600
NODE_WIDTH = 1080
NODE_HEIGHT = 150
VERTICAL_GAP = 105
MARGIN_Y = 130
LINE_WIDTH = 4


@dataclass(frozen=True)
class ExperimentSeries:
    name: str
    labels: tuple[str, ...]
    values: tuple[float, ...]


_SUMMARY_RESULT_RE = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._+\-]*)\s*上[，,]\s*"
    r"(?P<labels>.+?)的(?:六任务|多任务)?平均(?:准确率|精度|得分)"
    r"(?:依次为|分别为)(?P<values>[^。；;]+)"
)


def extract_experiment_series(items: list[str]) -> list[ExperimentSeries]:
    """Extract comparable disclosed metrics without reading or reusing paper images."""

    groups: dict[tuple[str, ...], list[ExperimentSeries]] = {}
    for item in items:
        match = _SUMMARY_RESULT_RE.search(item)
        if not match:
            continue
        labels = tuple(
            part.strip()
            for part in re.split(r"\s*(?:、|，|,|和|及)\s*", match.group("labels"))
            if part.strip()
        )
        values = tuple(float(value) for value in re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", match.group("values")))
        if len(labels) < 2 or len(labels) != len(values):
            continue
        groups.setdefault(labels, []).append(
            ExperimentSeries(name=match.group("name"), labels=labels, values=values)
        )
    if not groups:
        return []
    return max(groups.values(), key=lambda series: (len(series), len(series[0].labels)))[:3]


def _contains_chinese(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _clean_text(value: str, limit: int = 48) -> str:
    value = re.sub(r"\s+", " ", value).strip(" 。；;:")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _step_node(step: str, index: int) -> PatentFigureNode:
    match = re.match(r"\s*(S\d{3})\s*[：:]?\s*(.*)", step, re.IGNORECASE)
    code = match.group(1).upper() if match else f"S{100 + index}"
    body = match.group(2) if match else step
    description = _clean_text(body) if _contains_chinese(body) else "执行对应技术处理"
    return PatentFigureNode(node_id=f"step_{index}", label=f"{code}  {description}")


def build_default_patent_figures(solution: TechnicalSolution) -> list[PatentFigure]:
    """Create patent-oriented figure specifications without reading source image bytes."""

    method_nodes = [
        PatentFigureNode(node_id="method_input", label="获取输入数据", kind="data"),
        *[_step_node(step, index) for index, step in enumerate(solution.method_steps[:8], start=1)],
        PatentFigureNode(node_id="method_output", label="输出处理结果", kind="data"),
    ]
    method_edges = [
        PatentFigureEdge(source=left.node_id, target=right.node_id)
        for left, right in zip(method_nodes, method_nodes[1:])
    ]
    figures = [
        PatentFigure(
            figure_no=1,
            title="本发明方法的总体流程图",
            kind="flowchart",
            nodes=method_nodes,
            edges=method_edges,
        )
    ]

    if solution.components:
        component_nodes = [
            PatentFigureNode(node_id="system_input", label="输入数据接口", kind="data"),
        ]
        for index, component in enumerate(solution.components[:6], start=1):
            name = component.split("：", 1)[0].split(":", 1)[0]
            label = _clean_text(name, 24) if _contains_chinese(name) else f"第{index}处理模块"
            component_nodes.append(
                PatentFigureNode(
                    node_id=f"component_{index}",
                    label=f"{100 + index * 10}  {label}",
                    kind="component",
                )
            )
        component_nodes.append(PatentFigureNode(node_id="system_output", label="输出数据接口", kind="data"))
        figures.append(
            PatentFigure(
                figure_no=2,
                title="本发明系统的结构示意图",
                kind="system",
                nodes=component_nodes,
                edges=[
                    PatentFigureEdge(source=left.node_id, target=right.node_id)
                    for left, right in zip(component_nodes, component_nodes[1:])
                ],
            )
        )
    return figures


def ensure_patent_figures(
    figures: list[PatentFigure], solution: TechnicalSolution
) -> list[PatentFigure]:
    valid = [figure for figure in figures if len(figure.nodes) >= 2]
    result = valid[:4] or build_default_patent_figures(solution)
    for index, figure in enumerate(result, start=1):
        figure.figure_no = index
        if not _contains_chinese(figure.title):
            figure.title = "本发明方法的总体流程图" if figure.kind == "flowchart" else "本发明系统的结构示意图"
        original_to_normalized: dict[str, str] = {}
        normalized_nodes: list[PatentFigureNode] = []
        for node_index, node in enumerate(figure.nodes[:10], start=1):
            node_id = f"node_{node_index}"
            original_to_normalized.setdefault(node.node_id, node_id)
            if not _contains_chinese(node.label):
                prefix = f"S{100 + node_index}" if figure.kind == "flowchart" else str(100 + node_index * 10)
                node.label = f"{prefix}  执行对应技术处理"
            node.node_id = node_id
            normalized_nodes.append(node)
        if figure.kind == "flowchart":
            step_number = 101
            for node in normalized_nodes:
                if re.match(r"^S\d{3}\b", node.label, re.IGNORECASE):
                    node.label = re.sub(r"^S\d{3}\b", f"S{step_number}", node.label, count=1, flags=re.IGNORECASE)
                    step_number += 1
        normalized_edges: list[PatentFigureEdge] = []
        for edge in figure.edges:
            source = original_to_normalized.get(edge.source)
            target = original_to_normalized.get(edge.target)
            if source and target and source != target:
                normalized_edges.append(PatentFigureEdge(source=source, target=target, label=edge.label))
        figure.nodes = normalized_nodes
        figure.edges = normalized_edges or [
            PatentFigureEdge(source=left.node_id, target=right.node_id)
            for left, right in zip(normalized_nodes, normalized_nodes[1:])
        ]
        figure.image_path = None
        figure.mermaid_path = None
    return result


def drawing_descriptions(figures: list[PatentFigure]) -> list[str]:
    return [f"图{figure.figure_no}为{figure.title.rstrip('。')}。" for figure in figures]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, value: str, font: ImageFont.ImageFont, width: int) -> str:
    lines: list[str] = []
    current = ""
    for char in value:
        candidate = current + char
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


def _draw_node(
    draw: ImageDraw.ImageDraw,
    node: PatentFigureNode,
    box: tuple[int, int, int, int],
    font: ImageFont.ImageFont,
) -> None:
    left, top, right, bottom = box
    if node.kind == "start_end":
        draw.rounded_rectangle(box, radius=55, fill="white", outline="black", width=LINE_WIDTH)
    elif node.kind == "decision":
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        draw.polygon(
            [(center_x, top), (right, center_y), (center_x, bottom), (left, center_y)],
            fill="white",
            outline="black",
            width=LINE_WIDTH,
        )
    elif node.kind == "data":
        offset = 45
        draw.polygon(
            [(left + offset, top), (right, top), (right - offset, bottom), (left, bottom)],
            fill="white",
            outline="black",
        )
        draw.line(
            [(left + offset, top), (right, top), (right - offset, bottom), (left, bottom), (left + offset, top)],
            fill="black",
            width=LINE_WIDTH,
            joint="curve",
        )
    else:
        draw.rectangle(box, fill="white", outline="black", width=LINE_WIDTH)
        if node.kind == "component":
            draw.rectangle((left + 12, top + 12, right - 12, bottom - 12), outline="black", width=2)

    text = _wrap(draw, _clean_text(node.label, 52), font, right - left - 150)
    draw.multiline_text(
        ((left + right) / 2, (top + bottom) / 2),
        text,
        fill="black",
        font=font,
        anchor="mm",
        align="center",
        spacing=8,
    )


def _arrow_head(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 24
    spread = 0.55
    points = [
        end,
        (int(end[0] - length * math.cos(angle - spread)), int(end[1] - length * math.sin(angle - spread))),
        (int(end[0] - length * math.cos(angle + spread)), int(end[1] - length * math.sin(angle + spread))),
    ]
    draw.polygon(points, fill="black")


def _draw_edge(
    draw: ImageDraw.ImageDraw,
    start_box: tuple[int, int, int, int],
    end_box: tuple[int, int, int, int],
    label: str,
    font: ImageFont.ImageFont,
) -> None:
    source_center = ((start_box[0] + start_box[2]) // 2, (start_box[1] + start_box[3]) // 2)
    target_center = ((end_box[0] + end_box[2]) // 2, (end_box[1] + end_box[3]) // 2)
    if abs(source_center[1] - target_center[1]) < NODE_HEIGHT:
        if source_center[0] < target_center[0]:
            start = (start_box[2], source_center[1])
            end = (end_box[0], target_center[1])
        else:
            start = (start_box[0], source_center[1])
            end = (end_box[2], target_center[1])
        points = [start, end]
    else:
        start = (source_center[0], start_box[3])
        end = (target_center[0], end_box[1])
        if abs(start[0] - end[0]) > 80:
            bend_y = (start[1] + end[1]) // 2
            points = [start, (start[0], bend_y), (end[0], bend_y), end]
        else:
            points = [start, end]
    draw.line(points, fill="black", width=LINE_WIDTH, joint="curve")
    _arrow_head(draw, points[-2], points[-1])
    if label:
        midpoint = ((points[0][0] + points[1][0]) // 2 + 16, (points[0][1] + points[1][1]) // 2)
        draw.text(midpoint, _clean_text(label, 12), fill="black", font=font, anchor="lm")


def _optional_branch(
    nodes: list[PatentFigureNode], edges: list[PatentFigureEdge]
) -> tuple[str, str, str] | None:
    node_ids = {node.node_id for node in nodes}
    edge_pairs = {(edge.source, edge.target) for edge in edges}
    for node in nodes:
        if node.kind != "decision":
            continue
        targets = [edge.target for edge in edges if edge.source == node.node_id and edge.target in node_ids]
        if len(targets) != 2:
            continue
        first, second = targets
        if (first, second) in edge_pairs:
            return node.node_id, first, second
        if (second, first) in edge_pairs:
            return node.node_id, second, first
    return None


def _render_png(figure: PatentFigure, output_path: Path) -> None:
    nodes = figure.nodes[:10]
    branch = _optional_branch(nodes, figure.edges)
    branch_node_id = branch[1] if branch else None
    main_nodes = [node for node in nodes if node.node_id != branch_node_id]
    extra_branch_row = 1 if branch else 0
    height = (
        MARGIN_Y * 2
        + (len(main_nodes) + extra_branch_row) * NODE_HEIGHT
        + max(0, len(main_nodes) + extra_branch_row - 1) * VERTICAL_GAP
    )
    canvas_width = 2200 if branch else CANVAS_WIDTH
    image = Image.new("L", (canvas_width, height), color="white")
    draw = ImageDraw.Draw(image)
    node_font = _font(34)
    edge_font = _font(25)
    left = 180 if branch else (canvas_width - NODE_WIDTH) // 2
    boxes: dict[str, tuple[int, int, int, int]] = {}
    top = MARGIN_Y
    for node in main_nodes:
        boxes[node.node_id] = (left, top, left + NODE_WIDTH, top + NODE_HEIGHT)
        top += NODE_HEIGHT + VERTICAL_GAP
        if branch and node.node_id == branch[0]:
            top += NODE_HEIGHT + VERTICAL_GAP
    if branch:
        decision_box = boxes[branch[0]]
        branch_width = 720
        branch_top = decision_box[3] + VERTICAL_GAP
        boxes[branch[1]] = (canvas_width - branch_width - 90, branch_top, canvas_width - 90, branch_top + NODE_HEIGHT)

    valid_edges = [edge for edge in figure.edges if edge.source in boxes and edge.target in boxes]
    if not valid_edges:
        valid_edges = [
            PatentFigureEdge(source=left_node.node_id, target=right_node.node_id)
            for left_node, right_node in zip(nodes, nodes[1:])
        ]
    for edge in valid_edges:
        _draw_edge(draw, boxes[edge.source], boxes[edge.target], edge.label, edge_font)
    for node in nodes:
        _draw_node(draw, node, boxes[node.node_id], node_font)
    image.save(output_path, format="PNG", dpi=(300, 300), optimize=True)


def _mermaid_node(node: PatentFigureNode) -> str:
    label = _clean_text(node.label, 52).replace('"', "'").replace("\n", "<br/>")
    if node.kind == "start_end":
        return f'{node.node_id}(["{label}"])'
    if node.kind == "decision":
        return f'{node.node_id}{{"{label}"}}'
    if node.kind == "data":
        return f'{node.node_id}[/"{label}"/]'
    return f'{node.node_id}["{label}"]'


def _mermaid(figure: PatentFigure) -> str:
    direction = "TD"
    lines = [
        "%% 专利附图可编辑源文件；由技术方案重新生成，未复用论文原图",
        f"flowchart {direction}",
    ]
    node_ids = {node.node_id for node in figure.nodes[:10]}
    lines.extend(f"    {_mermaid_node(node)}" for node in figure.nodes[:10])
    for edge in figure.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            continue
        connector = f"-->|{_clean_text(edge.label, 12)}|" if edge.label else "-->"
        lines.append(f"    {edge.source} {connector} {edge.target}")
    lines.append("    classDef patent fill:#fff,stroke:#000,color:#000,stroke-width:2px;")
    lines.append(f"    class {','.join(node_ids)} patent;")
    return "\n".join(lines) + "\n"


def _draw_hatched_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    series_index: int,
) -> None:
    left, top, right, bottom = box
    fills = ("white", "#d9d9d9", "#a6a6a6")
    draw.rectangle(box, fill=fills[series_index % len(fills)], outline="black", width=3)
    if series_index == 0:
        return
    spacing = 18 if series_index == 1 else 12
    for offset in range(left - (bottom - top), right + (bottom - top), spacing):
        start_x = max(left, offset)
        start_y = bottom - max(0, left - offset)
        end_x = min(right, offset + (bottom - top))
        end_y = bottom - (end_x - offset)
        if start_y >= top and end_y <= bottom:
            draw.line((start_x, start_y, end_x, end_y), fill="#777777", width=1)


def render_experiment_chart(
    series: list[ExperimentSeries],
    output_dir: Path,
    figure_no: int,
) -> Path | None:
    """Redraw disclosed comparison data as a monochrome patent-style chart."""

    if not series or not series[0].labels:
        return None
    labels = series[0].labels
    comparable = [item for item in series if item.labels == labels]
    if not comparable:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"figure-{figure_no}.png"
    csv_path = output_dir / f"figure-{figure_no}.csv"
    all_values = [value for item in comparable for value in item.values]
    axis_min = max(0, math.floor(min(all_values) - 2))
    axis_max = min(100, math.ceil(max(all_values) + 2))
    if axis_max - axis_min < 6:
        axis_max = min(100, axis_min + 6)

    width, height = 1900, 1080
    plot_left, plot_top, plot_right, plot_bottom = 180, 180, 1810, 820
    image = Image.new("L", (width, height), color="white")
    draw = ImageDraw.Draw(image)
    axis_font = _font(28)
    label_font = _font(27)
    value_font = _font(24)
    legend_font = _font(28)

    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill="black", width=4)
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill="black", width=4)
    tick_step = max(1, math.ceil((axis_max - axis_min) / 5))
    ticks = list(range(axis_min, axis_max + 1, tick_step))
    if ticks[-1] != axis_max:
        ticks.append(axis_max)
    for tick in ticks:
        ratio = (tick - axis_min) / max(1, axis_max - axis_min)
        y = round(plot_bottom - ratio * (plot_bottom - plot_top))
        draw.line((plot_left - 10, y, plot_right, y), fill="#bfbfbf", width=1)
        draw.text((plot_left - 22, y), str(tick), fill="black", font=axis_font, anchor="rm")

    group_width = (plot_right - plot_left) / len(labels)
    bar_gap = 12
    bar_width = min(92, int((group_width - 70) / max(1, len(comparable))))
    for label_index, label in enumerate(labels):
        group_center = plot_left + group_width * (label_index + 0.5)
        total_width = len(comparable) * bar_width + (len(comparable) - 1) * bar_gap
        first_left = int(group_center - total_width / 2)
        for series_index, item in enumerate(comparable):
            value = item.values[label_index]
            ratio = (value - axis_min) / max(1, axis_max - axis_min)
            top = round(plot_bottom - ratio * (plot_bottom - plot_top))
            left = first_left + series_index * (bar_width + bar_gap)
            right = left + bar_width
            _draw_hatched_bar(draw, (left, top, right, plot_bottom), series_index)
            draw.text(((left + right) // 2, top - 12), f"{value:.1f}", fill="black", font=value_font, anchor="mb")
        wrapped = label.replace("-", "-\n", 1) if len(label) > 10 else label
        draw.multiline_text(
            (group_center, plot_bottom + 25),
            wrapped,
            fill="black",
            font=label_font,
            anchor="ma",
            align="center",
            spacing=3,
        )

    legend_x = plot_left
    for series_index, item in enumerate(comparable):
        box = (legend_x, 65, legend_x + 70, 110)
        _draw_hatched_bar(draw, box, series_index)
        draw.text((legend_x + 88, 87), item.name, fill="black", font=legend_font, anchor="lm")
        legend_x += 88 + int(draw.textlength(item.name, font=legend_font)) + 80
    draw.text((plot_left, 145), "平均准确率（%）", fill="black", font=axis_font, anchor="ls")
    draw.text((width // 2, 1010), "干预方式", fill="black", font=axis_font, anchor="mm")
    image.save(image_path, format="PNG", dpi=(300, 300), optimize=True)

    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["干预方式", *[item.name for item in comparable]])
        for index, label in enumerate(labels):
            writer.writerow([label, *[f"{item.values[index]:.1f}" for item in comparable]])

    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else []
    manifest.append(
        {
            "figure_no": figure_no,
            "title": "不同向量来源与适配方式的平均准确率对比图",
            "kind": "experiment_chart",
            "png": image_path.name,
            "data": csv_path.name,
            "source_policy": "由论文披露的结构化实验数据重新绘制，未复制或嵌入论文原始图片",
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return image_path


def render_patent_figures(figures: list[PatentFigure], output_dir: Path) -> list[PatentFigure]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("figure-*"):
        if path.is_file() and path.suffix.lower() in {".png", ".mmd", ".csv"}:
            path.unlink()
    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file():
        manifest_path.unlink()
    manifest: list[dict[str, object]] = []
    for index, figure in enumerate(figures, start=1):
        figure.figure_no = index
        stem = f"figure-{index}"
        image_path = output_dir / f"{stem}.png"
        mermaid_path = output_dir / f"{stem}.mmd"
        _render_png(figure, image_path)
        mermaid_path.write_text(_mermaid(figure), encoding="utf-8")
        figure.image_path = str(image_path.resolve())
        figure.mermaid_path = str(mermaid_path.resolve())
        manifest.append(
            {
                "figure_no": index,
                "title": figure.title,
                "kind": figure.kind,
                "png": image_path.name,
                "mermaid": mermaid_path.name,
                "source_policy": "由结构化技术方案重新生成，未复制或嵌入论文原始图片",
            }
        )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return figures
