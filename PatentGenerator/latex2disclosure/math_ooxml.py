from __future__ import annotations

import re
from collections.abc import Iterable

from docx.oxml import OxmlElement
from docx.oxml.ns import qn


_GREEK = {
    "delta": "δ",
    "theta": "θ",
    "mu": "μ",
    "lambda": "λ",
    "sigma": "σ",
    "gamma": "γ",
    "alpha": "α",
    "beta": "β",
}

_SYMBOLS = {
    "in": "∈",
    "cdot": "·",
    "times": "×",
    "le": "≤",
    "ge": "≥",
    "approx": "≈",
    "neq": "≠",
    "lVert": "‖",
    "rVert": "‖",
    "mid": "|",
    "quad": "  ",
    "qquad": "    ",
}


# Online agents are asked to emit $...$ math. These mappings keep older jobs
# compatible and replace their ASCII underscore/caret notation before export.
_LEGACY_FORMULAS = {
    "r_l=(1/N)Σ_i[(1/|A_i|)Σ_{a∈A_i}(h_l(a;C_R,i)-h_l(a;C_S,i))]": (
        r"\boldsymbol{r}_l=\frac{1}{N}\sum_{i=1}^{N}\frac{1}{|\mathcal{A}_i|}"
        r"\sum_{a\in\mathcal{A}_i}[\boldsymbol{h}_l(a;\mathcal{C}_{R,i})"
        r"-\boldsymbol{h}_l(a;\mathcal{C}_{S,i})]"
    ),
    "v_Attn^(l,m)=(1/N)Σ_i[(1/|A_i|)Σ_{a∈A_i}(o_R,i^(l,m)(a)-o_S,i^(l,m)(a))]": (
        r"\boldsymbol{v}_{\mathrm{Attn}}^{(l,m)}=\frac{1}{N}\sum_{i=1}^{N}"
        r"\frac{1}{|\mathcal{A}_i|}\sum_{a\in\mathcal{A}_i}"
        r"[\boldsymbol{o}_{R,i}^{(l,m)}(a)-\boldsymbol{o}_{S,i}^{(l,m)}(a)]"
    ),
    "δ_l(a)=h_l(a;C_R)-h_l(a;C_S)": (
        r"\boldsymbol{\delta}_l(a)=\boldsymbol{h}_l(a;\mathcal{C}_R)"
        r"-\boldsymbol{h}_l(a;\mathcal{C}_S)"
    ),
    "L_rec=||z_l^R-z_l^S||_2^2": (
        r"\mathcal{L}_{\mathrm{rec}}=\lVert\boldsymbol{z}_l^{R}"
        r"-\boldsymbol{z}_l^{S}\rVert_2^2"
    ),
    "õ^(l,m)(t)=o^(l,m)(t)+μv_Attn^(l,m)": (
        r"\widetilde{\boldsymbol{o}}^{(l,m)}(t)=\boldsymbol{o}^{(l,m)}(t)"
        r"+\mu\boldsymbol{v}_{\mathrm{Attn}}^{(l,m)}"
    ),
    "R={r_l}_{l=1}^L": r"\mathcal{R}=\{\boldsymbol{r}_l\}_{l=1}^{L}",
    "x̃_l=x_l+μr_l": r"\widetilde{\boldsymbol{x}}_l=\boldsymbol{x}_l+\mu\boldsymbol{r}_l",
    "x̃_l=x_l+θ_l": r"\widetilde{\boldsymbol{x}}_l=\boldsymbol{x}_l+\boldsymbol{\theta}_l",
    "L=λ_rec L_rec": r"\mathcal{L}=\lambda_{\mathrm{rec}}\mathcal{L}_{\mathrm{rec}}",
    "o_R,i^(l,m)(a)": r"\boldsymbol{o}_{R,i}^{(l,m)}(a)",
    "o_S,i^(l,m)(a)": r"\boldsymbol{o}_{S,i}^{(l,m)}(a)",
    "v_Attn^(l,m)": r"\boldsymbol{v}_{\mathrm{Attn}}^{(l,m)}",
    "õ^(l,m)(t)": r"\widetilde{\boldsymbol{o}}^{(l,m)}(t)",
    "o^(l,m)(t)": r"\boldsymbol{o}^{(l,m)}(t)",
    "h_l(a;C_R)": r"\boldsymbol{h}_l(a;\mathcal{C}_R)",
    "h_l(a;C_S)": r"\boldsymbol{h}_l(a;\mathcal{C}_S)",
    "h_l(a;C)": r"\boldsymbol{h}_l(a;\mathcal{C})",
    "C_R=(Q,T,A)": r"\mathcal{C}_R=(Q,T,A)",
    "C_S=(Q,A)": r"\mathcal{C}_S=(Q,A)",
    "z_l^R": r"\boldsymbol{z}_l^R",
    "z_l^S": r"\boldsymbol{z}_l^S",
    "δ_l(a)": r"\boldsymbol{\delta}_l(a)",
    "x̃_l": r"\widetilde{\boldsymbol{x}}_l",
    "x_l": r"\boldsymbol{x}_l",
    "θ_l": r"\boldsymbol{\theta}_l",
    "r_l": r"\boldsymbol{r}_l",
    "λ_rec": r"\lambda_{\mathrm{rec}}",
    "1×10^-4": r"1\times10^{-4}",
    "1×10^-3": r"1\times10^{-3}",
    "(Q,T,A)": r"(Q,T,A)",
    "(Q,A)": r"(Q,A)",
    "C_R": r"\mathcal{C}_R",
    "C_S": r"\mathcal{C}_S",
    "μ": r"\mu",
}

_LEGACY_PATTERN = re.compile(
    "|".join(re.escape(item) for item in sorted(_LEGACY_FORMULAS, key=len, reverse=True))
)


def normalize_math_markup(text: str) -> str:
    """Convert legacy linear math spans to explicit $...$ LaTeX markup."""

    if not text:
        return text
    pieces = re.split(r"(\$[^$]+\$)", text)
    for index in range(0, len(pieces), 2):
        pieces[index] = _LEGACY_PATTERN.sub(
            lambda match: f"${_LEGACY_FORMULAS[match.group(0)]}$",
            pieces[index],
        )
        pieces[index] = re.sub(r"(?<=层)([lL])(?=[^A-Za-z]|$)", r"$\1$", pieces[index])
        pieces[index] = re.sub(r"(?<=词元)([ait])(?=[^A-Za-z]|$)", r"$\1$", pieces[index])
        pieces[index] = re.sub(r"(?<=包含)(N)(?=个)", r"$\1$", pieces[index])
        pieces[index] = re.sub(r"(?<=第)(i)(?=个)", r"$\1$", pieces[index])
        pieces[index] = re.sub(r"(?<=头)(m)(?=[^A-Za-z]|$)", r"$\1$", pieces[index])
        pieces[index] = re.sub(r"(?<=位置)(t)(?=[^A-Za-z]|$)", r"$\1$", pieces[index])
    return "".join(pieces)


def _m(tag: str, text: str | None = None):
    element = OxmlElement(f"m:{tag}")
    if text is not None:
        element.text = text
    return element


def _math_run(
    text: str,
    *,
    bold: bool = False,
    normal: bool = False,
    script: str | None = None,
):
    run = _m("r")
    math_props = _m("rPr")
    if normal:
        style = _m("sty")
        style.set(qn("m:val"), "p")
        math_props.append(style)
    if script:
        script_element = _m("scr")
        script_element.set(qn("m:val"), script)
        math_props.append(script_element)
    if len(math_props):
        run.append(math_props)
    word_props = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    # Fill every Word font slot so CJK-oriented Word/WPS installations do not
    # substitute an East Asian font for Greek letters or math operators.
    for slot in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{slot}"), "Cambria Math")
    word_props.append(fonts)
    word_props.append(OxmlElement("w:noProof"))
    if bold:
        word_props.append(OxmlElement("w:b"))
    run.append(word_props)
    text_element = _m("t", text)
    if text.startswith(" ") or text.endswith(" "):
        text_element.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    run.append(text_element)
    return run


def _append_all(parent, children: Iterable) -> None:
    for child in children:
        parent.append(child)


def _script(base: list, subscript: list | None, superscript: list | None):
    if subscript is not None and superscript is not None:
        node = _m("sSubSup")
        node.append(_m("sSubSupPr"))
        base_element, sub_element, sup_element = _m("e"), _m("sub"), _m("sup")
        _append_all(base_element, base)
        _append_all(sub_element, subscript)
        _append_all(sup_element, superscript)
        _append_all(node, (base_element, sub_element, sup_element))
        return node
    if subscript is not None:
        node = _m("sSub")
        node.append(_m("sSubPr"))
        base_element, sub_element = _m("e"), _m("sub")
        _append_all(base_element, base)
        _append_all(sub_element, subscript)
        _append_all(node, (base_element, sub_element))
        return node
    node = _m("sSup")
    node.append(_m("sSupPr"))
    base_element, sup_element = _m("e"), _m("sup")
    _append_all(base_element, base)
    _append_all(sup_element, superscript or [])
    _append_all(node, (base_element, sup_element))
    return node


class _LatexMathParser:
    def __init__(self, source: str):
        self.source = source.strip()
        self.position = 0

    def parse(self, stop: str | None = None, *, bold: bool = False, normal: bool = False) -> list:
        nodes: list = []
        while self.position < len(self.source):
            char = self.source[self.position]
            if stop and char == stop:
                self.position += 1
                break
            if char.isspace():
                self.position += 1
                nodes.append(_math_run(" ", normal=True))
                continue
            atom = self._atom(bold=bold, normal=normal)
            subscript = superscript = None
            while self.position < len(self.source) and self.source[self.position] in "_^":
                marker = self.source[self.position]
                self.position += 1
                value = self._script_argument()
                if marker == "_":
                    subscript = value
                else:
                    superscript = value
            if subscript is not None or superscript is not None:
                if len(atom) == 1 and atom[0].tag == qn("m:nary"):
                    if subscript is not None:
                        _append_all(atom[0].find(qn("m:sub")), subscript)
                    if superscript is not None:
                        _append_all(atom[0].find(qn("m:sup")), superscript)
                else:
                    atom = [_script(atom, subscript, superscript)]
            nodes.extend(atom)
        return nodes

    def _script_argument(self) -> list:
        if self.position < len(self.source) and self.source[self.position] == "{":
            self.position += 1
            return self.parse("}")
        if self.position < len(self.source) and self.source[self.position] == "(":
            start = self.position
            depth = 0
            while self.position < len(self.source):
                char = self.source[self.position]
                self.position += 1
                depth += 1 if char == "(" else -1 if char == ")" else 0
                if depth == 0:
                    break
            return _LatexMathParser(self.source[start:self.position]).parse()
        return self._atom()

    def _group(self, *, bold: bool = False, normal: bool = False) -> list:
        if self.position >= len(self.source) or self.source[self.position] != "{":
            return []
        self.position += 1
        return self.parse("}", bold=bold, normal=normal)

    def _atom(self, *, bold: bool = False, normal: bool = False) -> list:
        char = self.source[self.position]
        if char == "{":
            return self._group(bold=bold, normal=normal)
        if char != "\\":
            self.position += 1
            if char.isdigit():
                start = self.position - 1
                while self.position < len(self.source) and (self.source[self.position].isdigit() or self.source[self.position] == "."):
                    self.position += 1
                return [_math_run(self.source[start:self.position], normal=True)]
            return [_math_run(char, bold=bold, normal=normal or not char.isalpha())]

        self.position += 1
        match = re.match(r"[A-Za-z]+", self.source[self.position:])
        if not match:
            escaped = self.source[self.position:self.position + 1]
            self.position += len(escaped)
            return [_math_run(escaped, normal=True)]
        command = match.group(0)
        self.position += len(command)
        if command == "frac":
            numerator = self._group()
            denominator = self._group()
            fraction = _m("f")
            fraction.append(_m("fPr"))
            num, den = _m("num"), _m("den")
            _append_all(num, numerator)
            _append_all(den, denominator)
            _append_all(fraction, (num, den))
            return [fraction]
        if command in {"boldsymbol", "mathbf"}:
            return self._group(bold=True)
        if command == "mathcal":
            content = self._group()
            for node in content:
                run_props = node.find(qn("m:rPr")) if node.tag == qn("m:r") else None
                if run_props is None and node.tag == qn("m:r"):
                    run_props = _m("rPr")
                    node.insert(0, run_props)
                if run_props is not None:
                    script_element = _m("scr")
                    script_element.set(qn("m:val"), "script")
                    run_props.append(script_element)
            return content
        if command in {"mathrm", "operatorname", "text"}:
            return self._group(normal=True)
        if command in {"tilde", "widetilde"}:
            accent = _m("acc")
            props = _m("accPr")
            accent_char = _m("chr")
            accent_char.set(qn("m:val"), "~")
            props.append(accent_char)
            base = _m("e")
            _append_all(base, self._group())
            _append_all(accent, (props, base))
            return [accent]
        if command == "sum":
            # A scripted summation run is interoperable with both Word and
            # LibreOffice and avoids an empty n-ary operand placeholder.
            return [_math_run("∑", normal=True)]
        if command in _GREEK:
            return [_math_run(_GREEK[command], bold=bold)]
        if command in _SYMBOLS:
            return [_math_run(_SYMBOLS[command], normal=True)]
        return [_math_run(command, normal=True)]


def math_element(latex: str):
    equation = _m("oMath")
    _append_all(equation, _LatexMathParser(latex).parse())
    return equation


def display_math_element(latex: str):
    equation_paragraph = _m("oMathPara")
    properties = _m("oMathParaPr")
    justification = _m("jc")
    justification.set(qn("m:val"), "center")
    properties.append(justification)
    equation_paragraph.append(properties)
    equation_paragraph.append(math_element(latex))
    return equation_paragraph


def append_rich_text(paragraph, text: str, *, size: float = 12, bold: bool = False, font_setter=None) -> None:
    """Append plain text and editable inline OMML equations to a paragraph."""

    normalized = normalize_math_markup(text or "待补充并由发明人确认。")
    for piece in re.split(r"(\$[^$]+\$)", normalized):
        if not piece:
            continue
        if piece.startswith("$") and piece.endswith("$"):
            paragraph._p.append(math_element(piece[1:-1]))
        else:
            run = paragraph.add_run(piece)
            if font_setter is not None:
                font_setter(run, size, bold=bold)


def contains_unmarked_math(text: str) -> bool:
    """Detect the most common unformatted variable conventions in generated prose."""

    plain = re.sub(r"\$[^$]+\$", "", text)
    return bool(
        re.search(
            r"(?:(?<![A-Za-z0-9_])(?:[A-Za-zΑ-ω]|delta|theta|lambda|mu|sigma)_[A-Za-z0-9]"
            r"|\^[({A-Za-z0-9-]|[Σ∑][_{A-Za-z])",
            plain,
        )
    )


def normalize_disclosure_math(disclosure):
    """Normalize every string field in a Pydantic disclosure model in place."""

    for field_name in type(disclosure).model_fields:
        value = getattr(disclosure, field_name)
        if isinstance(value, str):
            setattr(disclosure, field_name, normalize_math_markup(value))
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            setattr(disclosure, field_name, [normalize_math_markup(item) for item in value])
    return disclosure
