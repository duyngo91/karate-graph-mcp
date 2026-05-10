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
from karate_graph_analyzer.utils.db_dialect import DbDialectDetector

logger = logging.getLogger(__name__)


class DatabaseExtractor(IDependencyExtractor):
    """Extracts database operation dependencies from step text."""

    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        self.DB_PREFIXES = [
            re.compile(r"\b(db|database)\s*\.", re.IGNORECASE),
        ]
        self.DB_SQL_PATTERNS = [
            re.compile(r"\bSELECT\s+.*?\s+FROM\b", re.IGNORECASE),
            re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
            re.compile(r"\bUPDATE\s+.*?\s+SET\b", re.IGNORECASE),
            re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
            re.compile(r"\bCREATE\s+(TABLE|DATABASE|INDEX|VIEW)\b", re.IGNORECASE),
            re.compile(r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)\b", re.IGNORECASE),
            re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
            re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
            re.compile(r"\bUSE\s+[a-zA-Z_]\b", re.IGNORECASE),
        ]
        self.DB_PROVIDER_PATTERNS = [
            re.compile(r"\b(?:mongodb://|mongodb\+srv://|redis://|rediss://|neo4j://|bolt://)\b", re.IGNORECASE),
            re.compile(r"\b(?:mongodb|redis|dynamodb|cassandra|elasticsearch|opensearch|neo4j)\b", re.IGNORECASE),
            re.compile(r"\bdb\.[A-Za-z_][\w]*\.(?:find|findOne|insertOne|updateOne|deleteOne|aggregate)\b", re.IGNORECASE),
            re.compile(r"\b(?:GetItem|PutItem|UpdateItem|DeleteItem|BatchWriteItem|TableName)\b", re.IGNORECASE),
            re.compile(r"/_search\b|\b_search\b", re.IGNORECASE),
        ]

    def can_extract(self, step_text: str) -> bool:
        # Check for explicit prefixes first (highest confidence)
        if any(pattern.search(step_text) for pattern in self.DB_PREFIXES):
            return True
        # Check for structural SQL patterns
        if any(pattern.search(step_text) for pattern in self.DB_SQL_PATTERNS):
            return True
        return any(pattern.search(step_text) for pattern in self.DB_PROVIDER_PATTERNS)

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        details = self._parse_database_details(step_text)
        if not details and not self.can_extract(step_text):
            return []

        target_parts = []
        for key in ["provider", "host", "database", "table", "collection", "key", "index", "keyspace", "operation"]:
            if details.get(key):
                prefix = {
                    "provider": "Provider",
                    "host": "Host",
                    "database": "DB",
                    "table": "Table",
                    "collection": "Collection",
                    "key": "Key",
                    "index": "Index",
                    "keyspace": "Keyspace",
                    "operation": "Op",
                }[key]
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
        
        dialect_info = DbDialectDetector.detect(step_text)

        # Operation
        op_match = re.search(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE|USE)\b", step_text, re.IGNORECASE)
        if op_match:
            details["operation"] = op_match.group(1).upper()
        elif dialect_info.get("operation"):
            details["operation"] = dialect_info["operation"]

        # Table
        table_match = re.search(
            r"\b(FROM|INTO|UPDATE|JOIN|TABLE)\s+[`\"\[]?([a-zA-Z_][a-zA-Z0-9_.]*)[`\"\]]?",
            step_text,
            re.IGNORECASE,
        )
        if table_match:
            details["table"] = table_match.group(2)

        # Database
        db_match = re.search(r"\bUSE\s+([a-zA-Z_][a-zA-Z0-9_]*)", step_text, re.IGNORECASE) or \
                   re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*[a-zA-Z_][a-zA-Z0-9_]*", step_text)
        if db_match:
            details["database"] = db_match.group(1)

        # Host
        host_match = (
            re.search(r"(?:jdbc:(?:postgresql|mysql|mariadb|sqlserver|redshift|snowflake|clickhouse|db2)://)([^/\s'\";]+)", step_text, re.IGNORECASE)
            or re.search(r"jdbc:oracle:thin:@//([^/\s'\";:]+)", step_text, re.IGNORECASE)
            or re.search(r"(?:mongodb(?:\+srv)?://|redis(?:s)?://|postgresql://|mysql://|mariadb://|sqlserver://|neo4j://|bolt://)([^/\s'\";]+)", step_text, re.IGNORECASE)
            or re.search(r"host[=:\s]+['\"]?([^/\s'\";]+)", step_text, re.IGNORECASE)
        )
        if host_match:
            details["host"] = host_match.group(1)

        dialect_info = DbDialectDetector.detect(step_text, details)
        for key in ["db_type", "dialect", "provider", "dialect_confidence", "dialect_signals", "entity_type", "entity_name"]:
            value = dialect_info.get(key)
            if value and value != DbDialectDetector.UNKNOWN:
                details[key] = value
        entity_type = dialect_info.get("entity_type")
        entity_name = dialect_info.get("entity_name")
        if entity_type and entity_name:
            details.setdefault(entity_type, entity_name)

        return details
