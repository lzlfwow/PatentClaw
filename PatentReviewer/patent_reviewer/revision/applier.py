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
