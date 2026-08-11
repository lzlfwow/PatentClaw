from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

from .schemas import EvidenceSpan, FigureRecord, LatexPaper


SECTION_RE = re.compile(r"\\(section|subsection|subsubsection)\*?\{([^{}]+)\}")
INPUT_RE = re.compile(r"\\(?:input|include)\{([^{}]+)\}")
GRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_graphic(project_root: Path, reference: str) -> Path | None:
    raw = reference.strip()
    if not raw:
        return None
    candidate = project_root / raw
    candidates = [candidate]
    if not candidate.suffix:
        candidates.extend(candidate.with_suffix(ext) for ext in (".pdf", ".png", ".jpg", ".jpeg"))
    for path in candidates:
        if path.is_file() and _inside(path, project_root):
            return path.resolve()
    basename = Path(raw).name
    for path in project_root.rglob(f"{basename}.*" if not Path(raw).suffix else basename):
        if path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"} and _inside(path, project_root):
            return path.resolve()
    return None


def safe_extract_zip(archive: Path, destination: Path, max_expanded_bytes: int) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(archive) as handle:
        members = handle.infolist()
        if len(members) > 2000:
            raise ValueError("LaTeX工程文件数量超过2000，已拒绝解压")
        for member in members:
            total += member.file_size
            target = destination / member.filename
            if total > max_expanded_bytes:
                raise ValueError("LaTeX工程解压后超过大小限制")
            if member.is_dir():
                continue
            if not _inside(target, destination):
                raise ValueError(f"ZIP包含不安全路径: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _find_root_tex(root: Path) -> Path:
    tex_files = sorted(root.rglob("*.tex"))
    if not tex_files:
        raise ValueError("未在输入中找到.tex文件")
    preferred = [p for p in tex_files if p.name.lower() in {"main.tex", "paper.tex", "manuscript.tex"}]
    for path in preferred + tex_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "\\documentclass" in text and "\\begin{document}" in text:
            return path
    return preferred[0] if preferred else tex_files[0]


def prepare_latex_source(input_path: Path, workspace: Path, max_expanded_bytes: int) -> tuple[Path, Path]:
    input_path = input_path.resolve()
    source_root = workspace / "source"
    if source_root.exists():
        shutil.rmtree(source_root)
    source_root.mkdir(parents=True)
    if input_path.is_dir():
        shutil.copytree(input_path, source_root, dirs_exist_ok=True)
    elif input_path.suffix.lower() == ".zip":
        safe_extract_zip(input_path, source_root, max_expanded_bytes)
    elif input_path.suffix.lower() == ".tex":
        shutil.copy2(input_path, source_root / input_path.name)
        for sibling in input_path.parent.glob("*.bib"):
            shutil.copy2(sibling, source_root / sibling.name)
    else:
        raise ValueError("仅支持.tex文件、包含LaTeX工程的.zip文件或工程目录")
    source_root = source_root.resolve()
    root_tex = _find_root_tex(source_root).resolve()
    return source_root, root_tex


def _strip_comments(text: str) -> str:
    cleaned: list[str] = []
    for line in text.splitlines():
        cut = len(line)
        for index, char in enumerate(line):
            if char != "%":
                continue
            slash_count = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                slash_count += 1
                cursor -= 1
            if slash_count % 2 == 0:
                cut = index
                break
        cleaned.append(line[:cut])
    return "\n".join(cleaned)


def _expand_inputs(path: Path, project_root: Path, stack: tuple[Path, ...] = ()) -> tuple[str, list[str]]:
    path = path.resolve()
    if path in stack:
        return f"\n[Cyclic input skipped: {path.name}]\n", []
    if not _inside(path, project_root) or not path.exists():
        return f"\n[Missing input: {path.name}]\n", []
    text = _strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
    sources = [str(path.relative_to(project_root))]

    def replace(match: re.Match[str]) -> str:
        raw_name = match.group(1).strip()
        candidate = path.parent / raw_name
        if candidate.suffix == "":
            candidate = candidate.with_suffix(".tex")
        expanded, nested_sources = _expand_inputs(candidate, project_root, stack + (path,))
        sources.extend(nested_sources)
        return f"\n% BEGIN INPUT {raw_name}\n{expanded}\n% END INPUT {raw_name}\n"

    return INPUT_RE.sub(replace, text), list(dict.fromkeys(sources))


def _command_argument(text: str, command: str) -> str:
    marker = f"\\{command}"
    start = text.find(marker)
    while start >= 0:
        cursor = start + len(marker)
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] == "{":
            depth = 0
            for index in range(cursor, len(text)):
                if text[index] == "{" and (index == 0 or text[index - 1] != "\\"):
                    depth += 1
                elif text[index] == "}" and (index == 0 or text[index - 1] != "\\"):
                    depth -= 1
                    if depth == 0:
                        return text[cursor + 1 : index].strip()
        start = text.find(marker, start + len(marker))
    return ""


def _environment_blocks(text: str, names: tuple[str, ...]) -> list[str]:
    joined = "|".join(re.escape(name) for name in names)
    pattern = re.compile(rf"\\begin\{{({joined})\}}(.*?)\\end\{{\1\}}", re.DOTALL | re.IGNORECASE)
    return [match.group(2).strip() for match in pattern.finditer(text)]


def _latex_to_text(text: str) -> str:
    text = re.sub(r"\\(?:cite|citep|citet|ref|eqref|label)\{[^{}]*\}", " ", text)
    text = re.sub(r"\\(?:begin|end)\{[^{}]+\}", "\n", text)
    text = re.sub(r"\\(?:includegraphics)(?:\[[^\]]*\])?\{[^{}]*\}", " ", text)
    for _ in range(4):
        text = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", text)
    replacements = {
        "~": " ", "\\&": "&", "\\%": "%", "\\_": "_", "``": '"', "''": '"',
        "$": " ", "{": "", "}": "", "&": " | ", "\\\\": "\n",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _sections(expanded: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(expanded))
    if not matches:
        body_match = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", expanded, re.DOTALL)
        return {"正文": _latex_to_text(body_match.group(1) if body_match else expanded)}
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = _latex_to_text(match.group(2)) or f"Section {index + 1}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(expanded)
        body = _latex_to_text(expanded[match.end() : end])
        if body:
            result[title] = body
    return result


def _bibliography(root: Path, expanded: str) -> list[str]:
    entries = [_latex_to_text(item) for item in _environment_blocks(expanded, ("thebibliography",))]
    for bib_path in root.rglob("*.bib"):
        bib_text = bib_path.read_text(encoding="utf-8", errors="ignore")
        entries.extend(re.findall(r"title\s*=\s*[\{\"]([^}\"]+)", bib_text, re.IGNORECASE))
    return [entry for entry in entries if entry][:100]


def _build_evidence(
    sections: dict[str, str],
    root_file: str,
    *,
    equations: list[str],
    tables: list[str],
    algorithms: list[str],
    figures: list[FigureRecord],
    bibliography: list[str],
) -> list[EvidenceSpan]:
    evidence: list[EvidenceSpan] = []
    counter = 1
    for section, body in sections.items():
        chunks = [item.strip() for item in re.split(r"\n\n+|(?<=[。！？.!?])\s+", body) if len(item.strip()) >= 20]
        for chunk_index, chunk in enumerate(chunks):
            for offset in range(0, len(chunk), 900):
                part = chunk[offset : offset + 900].strip()
                if not part:
                    continue
                evidence.append(EvidenceSpan(
                    evidence_id=f"E{counter:04d}",
                    source_file=root_file,
                    section=section,
                    text=part,
                    locator=f"{section} / chunk {chunk_index + 1}",
                ))
                counter += 1

    structured_sources: tuple[tuple[str, list[str]], ...] = (
        ("Formula", equations),
        ("Table", tables),
        ("Algorithm", algorithms),
        ("Figure", [f"{item.label}: {item.caption}".strip(": ") for item in figures]),
        ("Reference", bibliography),
    )
    for category, items in structured_sources:
        for item_index, item in enumerate(items, start=1):
            text = item.strip()
            if not text:
                continue
            for part_index, offset in enumerate(range(0, len(text), 900), start=1):
                part = text[offset : offset + 900].strip()
                if not part:
                    continue
                evidence.append(EvidenceSpan(
                    evidence_id=f"E{counter:04d}",
                    source_file=root_file,
                    section=category,
                    text=part,
                    locator=f"{category} {item_index} / part {part_index}",
                ))
                counter += 1
    return evidence


def parse_latex_project(
    input_path: Path,
    workspace: Path,
    max_expanded_bytes: int = 150 * 1024 * 1024,
    max_chars: int = 300_000,
) -> tuple[LatexPaper, list[EvidenceSpan]]:
    project_root, root_tex = prepare_latex_source(input_path, workspace, max_expanded_bytes)
    expanded, source_files = _expand_inputs(root_tex, project_root)
    warnings: list[str] = []
    if len(expanded) > max_chars:
        expanded = expanded[:max_chars]
        warnings.append(f"展开后的LaTeX超过{max_chars}字符，已截断")
    title = _latex_to_text(_command_argument(expanded, "title")) or root_tex.stem
    abstracts = _environment_blocks(expanded, ("abstract",))
    abstract = _latex_to_text(abstracts[0]) if abstracts else ""
    sections = _sections(expanded)
    equations = _environment_blocks(expanded, ("equation", "equation*", "align", "align*", "gather"))
    tables = [_latex_to_text(item) for item in _environment_blocks(expanded, ("table", "table*", "tabular"))]
    algorithms = [_latex_to_text(item) for item in _environment_blocks(expanded, ("algorithm", "algorithmic", "algorithm2e"))]
    figures: list[FigureRecord] = []
    for block in _environment_blocks(expanded, ("figure", "figure*")):
        caption = _latex_to_text(_command_argument(block, "caption"))
        if not caption:
            continue
        label = _command_argument(block, "label")
        graphic_match = GRAPHICS_RE.search(block)
        asset = _resolve_graphic(project_root, graphic_match.group(1)) if graphic_match else None
        figures.append(FigureRecord(
            label=label,
            caption=caption,
            source_file=str(root_tex.relative_to(project_root)),
            asset_path=str(asset) if asset else None,
        ))
    plain_text = "\n\n".join([title, abstract, *[f"{name}\n{body}" for name, body in sections.items()]])
    paper = LatexPaper(
        root_file=str(root_tex.relative_to(project_root)),
        title=title,
        abstract=abstract,
        sections=sections,
        equations=equations[:100],
        tables=[item for item in tables if item][:50],
        algorithms=[item for item in algorithms if item][:30],
        figures=figures[:100],
        bibliography=_bibliography(project_root, expanded),
        plain_text=plain_text,
        source_files=source_files,
        warnings=warnings,
    )
    return paper, _build_evidence(
        sections,
        paper.root_file,
        equations=paper.equations,
        tables=paper.tables,
        algorithms=paper.algorithms,
        figures=paper.figures,
        bibliography=paper.bibliography,
    )
