"""Public check-engine namespace.

The first release keeps deterministic checks in ``patent_reviewer.rules`` and
exposes the engine here so future source, patent-law, and domain check packs can
be versioned independently without changing pipeline callers.
"""

from ..rules import RuleEngine

__all__ = ["RuleEngine"]
