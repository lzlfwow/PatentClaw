from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path

from ..schemas import SourceDocument

SECTION_RE = re.compile(r"\\(?:section|subsection|subsubsection)\*?\{([^}]*)\}")
TITLE_RE = re.compile(r"\\title\{([^}]*)\}", re.DOTALL)
ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
COMMAND_RE = re.compile(r"\\(?:cite|ref|label|textbf|emph|textit|mathrm|mathbf)\*?(?:\[[^]]*\])?\{([^{}]*)\}")
COMMENT_RE = re.compile(r"(?<!\\)%.*$")


def _clean_latex(text: str) -> str:
    text = "\n".join(COMMENT_RE.sub("", line) for line in text.splitlines())
    for _ in range(3):
        text = COMMAND_RE.sub(r"\1", text)
    text = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", " ", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?(?:\[[^]]*\])?", " ", text)
    text = text.replace("~", " ").replace("\\%", "%")
    return re.sub(r"\s+", " ", text).strip()


def _find_root(path: Path) -> Path:
    if path.is_file() and path.suffix.lower() == ".tex":
        return path
    candidates = list(path.rglob("*.tex"))
    if not candidates:
        raise ValueError(f"No .tex file found under {path}")
    return max(candidates, key=lambda p: ("\\documentclass" in p.read_text(errors="ignore"), p.stat().st_size))


def _read_with_inputs(root: Path, visited: set[Path] | None = None) -> str:
    visited = visited or set()
    resolved = root.resolve()
    if resolved in visited:
        return ""
    visited.add(resolved)
    text = root.read_text(encoding="utf-8", errors="ignore")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        child = root.parent / (name if name.endswith(".tex") else f"{name}.tex")
        return _read_with_inputs(child, visited) if child.exists() else match.group(0)

    return re.sub(r"\\(?:input|include)\{([^}]+)\}", replace, text)


def _parse(path: Path) -> SourceDocument:
    root = _find_root(path)
    raw = _read_with_inputs(root)
    title_match = TITLE_RE.search(raw)
    abstract_match = ABSTRACT_RE.search(raw)
    matches = list(SECTION_RE.finditer(raw))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        sections[_clean_latex(match.group(1))] = _clean_latex(raw[match.end() : end])
    return SourceDocument(
        root_file=str(root),
        title=_clean_latex(title_match.group(1)) if title_match else "",
        abstract=_clean_latex(abstract_match.group(1)) if abstract_match else "",
        sections=sections,
        equations=re.findall(r"\\begin\{(?:equation\*?|align\*?)\}(.*?)\\end\{(?:equation\*?|align\*?)\}", raw, re.DOTALL),
        tables=re.findall(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", raw, re.DOTALL),
        algorithms=re.findall(r"\\begin\{algorithm\*?\}(.*?)\\end\{algorithm\*?\}", raw, re.DOTALL),
        plain_text=_clean_latex(raw),
    )


def load_latex_source(source_path: str | Path) -> SourceDocument:
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".zip":
        return _parse(path)
    with tempfile.TemporaryDirectory(prefix="patent-reviewer-") as tmp:
        target = Path(tmp)
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                destination = (target / member.filename).resolve()
                if target.resolve() not in destination.parents and destination != target.resolve():
                    raise ValueError(f"Unsafe zip member: {member.filename}")
            archive.extractall(target)
        return _parse(target)

