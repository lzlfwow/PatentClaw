from __future__ import annotations

import re

from ..schemas import EvidenceSpan, ReviewInput


class EvidenceIndex:
    def __init__(self, review_input: ReviewInput) -> None:
        self._spans = review_input.evidence
        self._by_id = {span.evidence_id: span for span in self._spans}
        self._field_ids = review_input.generator_metadata.get("field_evidence_ids", {})

    def get(self, evidence_id: str) -> EvidenceSpan | None:
        return self._by_id.get(evidence_id)

    def search(self, text: str, limit: int = 5) -> list[EvidenceSpan]:
        tokens = self._tokens(text)
        if not tokens:
            return []
        ranked: list[tuple[float, EvidenceSpan]] = []
        for span in self._spans:
            haystack = span.text.lower()
            overlap = sum(1 for token in tokens if token in haystack)
            if overlap:
                ranked.append((overlap / len(tokens), span))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [span for _, span in ranked[:limit]]

    def ids_for(self, text: str, limit: int = 5) -> list[str]:
        return [span.evidence_id for span in self.search(text, limit)]

    def ids_for_field(self, field: str, text: str, limit: int = 5) -> list[str]:
        declared = [item for item in self._field_ids.get(field, []) if item in self._by_id]
        return declared[:limit] or self.ids_for(text, limit)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        ascii_tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text.lower())
        chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
        chinese_tokens = [chinese[i : i + 2] for i in range(max(0, len(chinese) - 1))]
        return list(dict.fromkeys(ascii_tokens + chinese_tokens))
