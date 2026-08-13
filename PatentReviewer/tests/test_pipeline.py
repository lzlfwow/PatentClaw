from __future__ import annotations

import json
from pathlib import Path

import pytest

from patent_reviewer.pipeline import run_review


def write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "paper.tex"
    source.write_text(r"""
\documentclass{article}
\title{面向设备异常检测的神经网络方法}
\begin{document}
\begin{abstract}通过传感器时序数据训练神经网络，并输出设备异常预测结果。\end{abstract}
\section{Method}
输入传感器时序数据，进行归一化处理，使用卷积层提取特征，并由分类层输出异常类别。
训练时采用交叉熵损失函数。推理时将异常类别发送至设备控制系统。
\section{Experiments}
实验表明该方法提高异常识别准确率并降低误报率。
\end{document}
""", encoding="utf-8")
    generator = tmp_path / "generator" / "artifacts"
    generator.mkdir(parents=True)
    disclosure = {
        "invention_title": "一种面向设备异常检测的神经网络方法",
        "technical_field": "本发明涉及设备状态监测和机器学习技术领域。",
        "background": ["现有设备异常检测对复杂时序模式的识别能力有限。"],
        "prior_art_defects": ["复杂工况下误报率较高。"],
        "technical_problem": ["提高设备异常识别准确率并降低误报率。"],
        "overall_solution": "本文提出一种处理传感器时序数据的神经网络异常检测方法。",
        "detailed_steps": ["获取传感器时序数据。", "对数据进行归一化。", "通过卷积层和分类层输出异常类别。"],
        "key_innovations": ["将卷积特征提取用于设备时序异常检测。"],
        "beneficial_effects": ["提高异常识别准确率并降低误报率。"],
        "embodiments": ["获取设备传感器时序数据，归一化后输入卷积层提取特征，由分类层输出异常类别；训练采用交叉熵损失，推理结果发送至设备控制系统，用于生成设备异常状态提示。"],
        "experimental_evidence": ["实验表明准确率提高且误报率降低。"],
        "drawing_descriptions": [], "terminology": [],
        "system_implementation": ["神经网络包括卷积层和分类层，训练采用交叉熵损失函数。"],
        "data_and_interfaces": ["输入为传感器时序数据，输出为设备异常类别。"],
        "implementation_boundaries": [], "alternatives": [], "inventor_confirmation_items": [],
    }
    evidence = [
        {"evidence_id": "E-1", "source_file": str(source), "section": "Method",
         "text": "输入传感器时序数据，进行归一化处理，使用卷积层提取特征，并由分类层输出异常类别。训练采用交叉熵损失函数。"},
        {"evidence_id": "E-2", "source_file": str(source), "section": "Experiments",
         "text": "实验表明该方法提高异常识别准确率并降低误报率。"},
    ]
    (generator / "job.json").write_text(json.dumps({"job_id": "g-1", "status": "completed", "disclosure": disclosure, "evidence": evidence}, ensure_ascii=False), encoding="utf-8")
    return generator, source


@pytest.mark.asyncio
async def test_offline_pipeline_exports_bundle_and_applies_safe_style_fix(tmp_path: Path) -> None:
    generator, source = write_fixture(tmp_path)
    job = await run_review(generator, source, output_root=tmp_path / "out", online=False)

    assert "本文" not in job.final_disclosure.overall_solution
    assert "本发明" in job.final_disclosure.overall_solution
    assert job.initial_report.findings
    assert len(job.initial_report.dimensions) == 13
    assert job.changes
    assert Path(job.artifacts["final_disclosure_docx"]).exists()
    assert Path(job.artifacts["initial_review_markdown"]).exists()
    assert Path(job.artifacts["job_json"]).exists()


@pytest.mark.asyncio
async def test_missing_required_section_is_not_fabricated(tmp_path: Path) -> None:
    generator, source = write_fixture(tmp_path)
    job_path = generator / "job.json"
    data = json.loads(job_path.read_text(encoding="utf-8"))
    data["disclosure"]["embodiments"] = []
    job_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    job = await run_review(generator, source, output_root=tmp_path / "out")

    assert job.final_disclosure.embodiments == []
    assert any(item.code == "NO_EMBODIMENT" for item in job.initial_report.findings)
    assert any(action.target_path == "embodiments" for action in job.revision_plan.blocked_actions)


@pytest.mark.asyncio
async def test_generator_field_evidence_mapping_avoids_cross_language_false_positive(tmp_path: Path) -> None:
    generator, source = write_fixture(tmp_path)
    job_path = generator / "job.json"
    data = json.loads(job_path.read_text(encoding="utf-8"))
    data["evidence"] = [{
        "evidence_id": "E-EN", "source_file": str(source), "section": "Method",
        "text": "The model consumes sensor time series and outputs an anomaly category.",
    }]
    data["understanding"] = {"evidence_ids": ["E-EN"]}
    data["solution"] = {"evidence_ids": ["E-EN"]}
    data["evidence_package"] = {"evidence_mapping": {"技术方案": ["E-EN"], "有益效果": ["E-EN"]}}
    job_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    job = await run_review(generator, source, output_root=tmp_path / "out")

    codes = {item.code for item in job.initial_report.findings}
    assert "NO_EVIDENCE_OVERALL_SOLUTION" not in codes
    assert "NO_EVIDENCE_BENEFICIAL_EFFECTS" not in codes
