"""
Database dependency extractor.

Strategy Pattern implementation for extracting database operation
dependencies from Karate step text.
"""

import logging
import re
from typing import Dict, List

from karate_graph_analyzer.interfaces import IDependencyExtractor
from karate_graph_analyzer.models import Dependency, DependencyType, ParserConfig

logger = logging.getLogger(__name__)


class DatabaseExtractor(IDependencyExtractor):
    """Extracts database operation dependencies from step text."""

    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        self.DB_KEYWORDS = [
            re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE)\b", re.IGNORECASE),
            re.compile(r"\b(db|database)\s*\.", re.IGNORECASE),
        ]

    def can_extract(self, step_text: str) -> bool:
        return any(pattern.search(step_text) for pattern in self.DB_KEYWORDS)

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        details = self._parse_database_details(step_text)
        if not details and not any(p.search(step_text) for p in self.DB_KEYWORDS):
            return []

        target_parts = []
        for key in ["host", "database", "table", "operation"]:
            if details.get(key):
                prefix = {"host": "Host", "database": "DB", "table": "Table", "operation": "Op"}[key]
                target_parts.append(f"{prefix}: {details[key]}")

        target = " | ".join(target_parts) or re.sub(r"\s+", " ", step_text[:50]).strip()

        return [Dependency(
            type=DependencyType.DATABASE,
            target=target,
            line_number=line_number,
            parameters=details,
        )]

    def _parse_database_details(self, step_text: str) -> Dict[str, str]:
        details = {}
        
        # Operation
        op_match = re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE)\b", step_text, re.IGNORECASE)
        if op_match: details["operation"] = op_match.group(1).upper()

        # Table
        table_match = re.search(r"\b(FROM|INTO|UPDATE|TABLE)\s+([a-zA-Z_][a-zA-Z0-9_]*)", step_text, re.IGNORECASE)
        if table_match: details["table"] = table_match.group(2)

        # Database
        db_match = re.search(r"\bUSE\s+([a-zA-Z_][a-zA-Z0-9_]*)", step_text, re.IGNORECASE) or \
                   re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*[a-zA-Z_][a-zA-Z0-9_]*", step_text)
        if db_match: details["database"] = db_match.group(1)

        # Host
        host_match = re.search(r"(?:jdbc:[a-z]+://|mongodb://|postgresql://|mysql://|host[=:\s]+['\"]?)([^/\s'\";\\s]+)", step_text, re.IGNORECASE)
        if host_match: details["host"] = host_match.group(1)

        return details
