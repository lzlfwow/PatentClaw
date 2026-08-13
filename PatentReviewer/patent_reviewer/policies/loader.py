from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReviewPolicy:
    data: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def baseline(self) -> str:
        return str(self.data["baseline"])

    @property
    def legal_references(self) -> dict[str, str]:
        return dict(self.data.get("legal_references", {}))


def load_policy(path: Path | None = None) -> ReviewPolicy:
    policy_path = path or Path(str(files("patent_reviewer.policies").joinpath("default_cn_invention.yaml")))
    return ReviewPolicy(json.loads(policy_path.read_text(encoding="utf-8")))
