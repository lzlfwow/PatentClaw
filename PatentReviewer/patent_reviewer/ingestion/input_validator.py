from __future__ import annotations

from ..schemas import ReviewInput


def validate_review_input(review_input: ReviewInput) -> list[str]:
    errors: list[str] = []
    if not review_input.disclosure.invention_title.strip():
        errors.append("Generator disclosure is missing invention_title")
    if not review_input.source.plain_text.strip():
        errors.append("LaTeX source did not yield readable text")
    if not review_input.evidence:
        errors.append("No source evidence could be built")
    return errors

