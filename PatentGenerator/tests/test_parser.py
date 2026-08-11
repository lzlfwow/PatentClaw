from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from latex2disclosure.latex_parser import parse_latex_project, safe_extract_zip


def test_multifile_latex_is_expanded_and_evidence_is_built(tmp_path: Path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "main.tex").write_text(
        r"""\documentclass{article}
\title{A Structured Exploration Method}
\begin{document}
\begin{abstract}We propose a structured method for robust candidate generation.</abstract>
\section{Introduction}Existing methods produce redundant candidates.
\input{method}
\section{Results}The method improves diversity while preserving validity.
\begin{equation}y = f(x)\end{equation}
\begin{figure}\includegraphics{pipeline.png}\caption{System pipeline.}\label{fig:system}\end{figure}
\end{document}""",
        encoding="utf-8",
    )
    (source / "method.tex").write_text(
        r"""\section{Method}The system obtains input data. It constructs a representation space. It samples candidates and filters redundant results. It outputs diverse valid results.""",
        encoding="utf-8",
    )
    (source / "pipeline.png").write_bytes(b"parser-only fixture")
    paper, evidence = parse_latex_project(source, tmp_path / "work")
    assert paper.title == "A Structured Exploration Method"
    assert "method.tex" in paper.source_files
    assert any("representation space" in body for body in paper.sections.values())
    assert paper.figures[0].caption == "System pipeline."
    assert paper.figures[0].asset_path is not None
    assert Path(paper.figures[0].asset_path).name == "pipeline.png"
    assert Path(paper.figures[0].asset_path).is_file()
    assert evidence and evidence[0].evidence_id == "E0001"
    assert any(item.section == "Formula" and "y = f(x)" in item.text for item in evidence)
    assert any(item.section == "Figure" and "System pipeline" in item.text for item in evidence)


def test_zip_slip_is_rejected(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.tex", "malicious")
    with pytest.raises(ValueError, match="不安全路径"):
        safe_extract_zip(archive, tmp_path / "out", 1024 * 1024)
