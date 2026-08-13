from __future__ import annotations

import re


def normalize_text(value: str) -> str:
    value = value.replace("\u3000", " ")
    return re.sub(r"\s+", " ", value).strip()


def tokenize_technical_text(value: str) -> set[str]:
    normalized = normalize_text(value).lower()
    ascii_tokens = set(re.findall(r"[a-z][a-z0-9_-]{2,}", normalized))
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", normalized)
    chinese_tokens = {chinese[i : i + 2] for i in range(max(0, len(chinese) - 1))}
    return ascii_tokens | chinese_tokens

