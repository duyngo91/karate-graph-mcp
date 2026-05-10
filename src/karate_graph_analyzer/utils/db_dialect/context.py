"""Value objects for database dialect detection."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


UNKNOWN = "unknown"


@dataclass(frozen=True)
class DbDialectContext:
    """Normalized DB dialect detection result."""

    db_type: str = UNKNOWN
    dialect: str = UNKNOWN
    provider: str = UNKNOWN
    dialect_confidence: str = UNKNOWN
    dialect_signals: Tuple[str, ...] = field(default_factory=tuple)
    operation: Optional[str] = None
    entity_type: Optional[str] = None
    entity_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "db_type": self.db_type,
            "dialect": self.dialect,
            "provider": self.provider,
            "dialect_confidence": self.dialect_confidence,
            "dialect_signals": list(self.dialect_signals),
            "operation": self.operation,
            "entity_type": self.entity_type,
            "entity_name": self.entity_name,
        }

    @classmethod
    def unknown(
        cls,
        operation: Optional[str] = None,
        signals: Optional[List[str]] = None,
    ) -> "DbDialectContext":
        return cls(operation=operation, dialect_signals=tuple(_unique(signals or [])))


def normalize_optional(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_token(value: Any, default: str = UNKNOWN) -> str:
    text = normalize_optional(value)
    return text.lower() if text else default


def unique_tuple(values: List[str]) -> Tuple[str, ...]:
    return tuple(_unique(values))


def _unique(values: List[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))
