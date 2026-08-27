from __future__ import annotations

from pathlib import Path

from PIL import Image

from latex2disclosure.patent_figures import (
    ensure_patent_figures,
    extract_experiment_series,
    render_experiment_chart,
    render_patent_figures,
)
from latex2disclosure.schemas import PatentFigure, PatentFigureEdge, PatentFigureNode, TechnicalSolution


def test_optional_branch_is_laid_out_beside_main_flow(tmp_path: Path):
    figure = PatentFigure(
        figure_no=1,
        title="带可选分支的方法流程图",
        kind="flowchart",
        nodes=[
            PatentFigureNode(node_id="start", label="开始", kind="start_end"),
            PatentFigureNode(node_id="decision", label="是否启用适配", kind="decision"),
            PatentFigureNode(node_id="optional", label="执行适配"),
            PatentFigureNode(node_id="merge", label="执行主流程"),
            PatentFigureNode(node_id="end", label="结束", kind="start_end"),
        ],
        edges=[
            PatentFigureEdge(source="start", target="decision"),
            PatentFigureEdge(source="decision", target="optional", label="是"),
            PatentFigureEdge(source="decision", target="merge", label="否"),
            PatentFigureEdge(source="optional", target="merge", label="适配结果"),
            PatentFigureEdge(source="merge", target="end"),
        ],
    )

    render_patent_figures([figure], tmp_path)

    with Image.open(tmp_path / "figure-1.png") as image:
        assert image.width == 2200
    source = (tmp_path / "figure-1.mmd").read_text(encoding="utf-8")
    assert "|是|" in source
    assert "|否|" in source


def test_flow_step_numbers_are_normalized_to_execution_order():
    figure = PatentFigure(
        figure_no=1,
        title="方法流程图",
        kind="flowchart",
        nodes=[
            PatentFigureNode(node_id="a", label="S101 获取输入"),
            PatentFigureNode(node_id="b", label="S107 执行可选适配"),
            PatentFigureNode(node_id="c", label="S105 注入向量"),
        ],
        edges=[PatentFigureEdge(source="a", target="b"), PatentFigureEdge(source="b", target="c")],
    )
    solution = TechnicalSolution(
        system_boundary="测试",
        components=[],
        method_steps=["S101：获取输入", "S102：执行可选适配", "S103：注入向量"],
        data_flow=[],
    )

    normalized = ensure_patent_figures([figure], solution)[0]

    assert [node.label.split()[0] for node in normalized.nodes] == ["S101", "S102", "S103"]


def test_experiment_metrics_are_redrawn_without_source_images(tmp_path: Path):
    evidence = [
        "Model-A上，基线、方法甲和方法乙的六任务平均准确率依次为66.6%、68.3%和69.1%。",
        "Model-B上，基线、方法甲和方法乙的六任务平均准确率依次为67.8%、69.0%和69.4%。",
    ]

    series = extract_experiment_series(evidence)
    chart_path = render_experiment_chart(series, tmp_path, 3)

    assert [item.name for item in series] == ["Model-A", "Model-B"]
    assert series[0].labels == ("基线", "方法甲", "方法乙")
    assert series[1].values == (67.8, 69.0, 69.4)
    assert chart_path == tmp_path / "figure-3.png"
    assert chart_path.is_file()
    assert (tmp_path / "figure-3.csv").is_file()
    assert "experiment_chart" in (tmp_path / "manifest.json").read_text(encoding="utf-8")
