"""Registry for database dialect strategies."""

from typing import Any, Dict, Iterable, Optional

from karate_graph_analyzer.utils.db_dialect.context import DbDialectContext
from karate_graph_analyzer.utils.db_dialect.strategies import (
    DbDialectStrategy,
    default_strategies,
    detect_operation,
)


class DbDialectRegistry:
    """Ordered registry of dialect detection strategies."""

    def __init__(self, strategies: Optional[Iterable[DbDialectStrategy]] = None) -> None:
        self._strategies = list(strategies) if strategies is not None else default_strategies()

    def register(self, strategy: DbDialectStrategy) -> None:
        self._strategies.append(strategy)

    def detect(self, text: str, details: Optional[Dict[str, Any]] = None) -> DbDialectContext:
        safe_details = details or {}
        for strategy in self._strategies:
            context = strategy.detect(text, safe_details)
            if context is not None:
                return context
        return DbDialectContext.unknown(operation=detect_operation(text))
