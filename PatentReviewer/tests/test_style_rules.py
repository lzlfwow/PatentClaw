from __future__ import annotations

from patent_reviewer.policies import load_policy
from patent_reviewer.rules import RuleEngine
from patent_reviewer.schemas import TechnicalDisclosure


def test_best_layer_with_explicit_evaluation_context_is_not_absolute_claim() -> None:
    engine = RuleEngine(load_policy())
    disclosure = TechnicalDisclosure(
        invention_title="一种测试方法",
        detailed_steps=["在留出开发集上评测候选层，并选择性能最佳的层作为注入层。"],
    )

    findings = engine._drafting_style(disclosure)

    assert not any(item.check_id == "WR-02" for item in findings)


def test_unqualified_best_effect_remains_absolute_claim() -> None:
    engine = RuleEngine(load_policy())
    disclosure = TechnicalDisclosure(
        invention_title="一种测试方法",
        beneficial_effects=["本发明获得最佳效果。"],
    )

    findings = engine._drafting_style(disclosure)

    assert any(item.check_id == "WR-02" for item in findings)
