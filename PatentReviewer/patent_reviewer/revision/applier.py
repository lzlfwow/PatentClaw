from __future__ import annotations

from copy import deepcopy

from ..schemas import ChangeRecord, RevisionPlan, TechnicalDisclosure


SAFE_REPLACEMENTS = {
    "本文": "本发明",
    "本论文": "本发明",
    "作者": "发明人",
    "我们提出": "本发明提出",
    "our paper": "本发明",
}


def apply_global_wording_replacements(
    disclosure: TechnicalDisclosure,
    *,
    allowed_paths: list[str],
    finding_ids: list[str],
    round_number: int,
    terms: list[str] | None = None,
) -> tuple[TechnicalDisclosure, list[ChangeRecord]]:
    """Apply safe, context-independent patent-voice replacements across fields."""

    data = deepcopy(disclosure.model_dump())
    changes: list[ChangeRecord] = []
    for path in allowed_paths:
        if path not in data:
            continue
        value = data[path]
        before = "\n".join(value) if isinstance(value, list) else str(value)
        after = before
        replacements = SAFE_REPLACEMENTS if terms is None else {
            source: target for source, target in SAFE_REPLACEMENTS.items() if source in terms
        }
        for source, target in replacements.items():
            after = after.replace(source, target)
        if after == before:
            continue
        data[path] = after.split("\n") if isinstance(value, list) else after
        changes.append(ChangeRecord(
            action_id=f"R{round_number}-WR-01-G{len(changes)+1:03d}",
            target_path=path,
            before=before,
            after=after,
            finding_ids=finding_ids,
        ))
    return TechnicalDisclosure.model_validate(data), changes


def apply_revision_plan(disclosure: TechnicalDisclosure, plan: RevisionPlan) -> tuple[TechnicalDisclosure, list[ChangeRecord]]:
    data = deepcopy(disclosure.model_dump())
    changes: list[ChangeRecord] = []
    for action in plan.actions:
        if action.operation != "replace" or action.target_path not in data:
            continue
        value = data[action.target_path]
        before_value = "\n".join(value) if isinstance(value, list) else str(value)
        replaced = _replace_known(value, action.before)
        after_value = "\n".join(replaced) if isinstance(replaced, list) else str(replaced)
        if before_value == after_value:
            continue
        data[action.target_path] = replaced
        action.applied = True
        changes.append(ChangeRecord(
            action_id=action.action_id, target_path=action.target_path, before=before_value,
            after=after_value, finding_ids=action.finding_ids,
        ))
    return TechnicalDisclosure.model_validate(data), changes


def _replace_known(value: str | list[str], term: str) -> str | list[str]:
    replacement = SAFE_REPLACEMENTS.get(term)
    if replacement is None:
        return value
    if isinstance(value, list):
        return [item.replace(term, replacement) for item in value]
    return value.replace(term, replacement)
