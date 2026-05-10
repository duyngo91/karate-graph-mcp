"""Facade for database dialect detection."""

from typing import Any, Dict, Optional

from karate_graph_analyzer.utils.db_dialect.context import UNKNOWN, DbDialectContext
from karate_graph_analyzer.utils.db_dialect.registry import DbDialectRegistry


class DbDialectDetector:
    """Backward-compatible facade over the default strategy registry."""

    UNKNOWN = UNKNOWN
    _registry = DbDialectRegistry()

    @classmethod
    def detect_context(
        cls,
        text: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> DbDialectContext:
        return cls._registry.detect(text, details)

    @classmethod
    def detect(cls, text: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return cls.detect_context(text, details).to_dict()

    @classmethod
    def with_registry(cls, registry: DbDialectRegistry) -> None:
        cls._registry = registry
