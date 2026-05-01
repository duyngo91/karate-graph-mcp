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
    """Extracts database operation dependencies from step text.

    Identifies SQL keywords and database interaction patterns:
    - SQL DML: SELECT, INSERT, UPDATE, DELETE
    - SQL DDL: CREATE, DROP, ALTER, TRUNCATE
    - Database method calls: db.*, database.*

    Extracts details:
    - Host/connection string
    - Database name
    - Table name
    - Operation type
    """

    # Database keyword patterns (compiled once)
    DB_KEYWORDS = [
        re.compile(r"\bSELECT\b", re.IGNORECASE),
        re.compile(r"\bINSERT\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\b", re.IGNORECASE),
        re.compile(r"\bDELETE\b", re.IGNORECASE),
        re.compile(r"\bCREATE\b", re.IGNORECASE),
        re.compile(r"\bDROP\b", re.IGNORECASE),
        re.compile(r"\bALTER\b", re.IGNORECASE),
        re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
        re.compile(r"\bdb\s*\.", re.IGNORECASE),
        re.compile(r"\bdatabase\s*\.", re.IGNORECASE),
    ]

    def __init__(self, config: ParserConfig) -> None:
        """Initialize with parser configuration.

        Args:
            config: Parser configuration (reserved for future database-specific config)
        """
        self.config = config

    def can_extract(self, step_text: str) -> bool:
        """Check if step contains database-related keywords."""
        return any(pattern.search(step_text) for pattern in self.DB_KEYWORDS)

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        """Extract database operation dependencies from step text.

        Args:
            step_text: The text of a Gherkin step
            line_number: Line number in the feature file

        Returns:
            List of extracted database dependencies (at most one per step)
        """
        return self._extract_database_dependencies(step_text, line_number)

    def _extract_database_dependencies(
        self, step_text: str, line_number: int
    ) -> List[Dependency]:
        """Extract database operation dependencies from step text."""
        dependencies: List[Dependency] = []

        for keyword in self.DB_KEYWORDS:
            if keyword.search(step_text):
                # Parse database details
                db_details = self._parse_database_details(step_text)

                # Create descriptive target name
                target_parts = []

                if db_details.get("host"):
                    target_parts.append(f"Host: {db_details['host']}")

                if db_details.get("database"):
                    target_parts.append(f"DB: {db_details['database']}")

                if db_details.get("table"):
                    target_parts.append(f"Table: {db_details['table']}")

                if db_details.get("operation"):
                    target_parts.append(f"Op: {db_details['operation']}")

                # Fallback to operation snippet if no details found
                if not target_parts:
                    operation = re.sub(r"\s+", " ", step_text[:50]).strip()
                    target_parts.append(operation)

                target = " | ".join(target_parts)

                dependencies.append(
                    Dependency(
                        type=DependencyType.DATABASE,
                        target=target,
                        line_number=line_number,
                        parameters=db_details,
                    )
                )
                break  # Only add one DB dependency per step

        return dependencies

    def _parse_database_details(self, step_text: str) -> Dict[str, str]:
        """Parse database connection details from step text.

        Extracts:
        - Host/connection string
        - Database name
        - Table name
        - Operation type

        Args:
            step_text: Step text to parse

        Returns:
            Dictionary with database details
        """
        details: Dict[str, str] = {}

        # Extract operation type (first SQL keyword found)
        operations = [
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE",
            "DROP",
            "ALTER",
            "TRUNCATE",
        ]
        for op in operations:
            if re.search(rf"\b{op}\b", step_text, re.IGNORECASE):
                details["operation"] = op
                break

        # Extract table name from SQL statements
        table_patterns = [
            r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            r"\bINTO\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            r"\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            r"\bTABLE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        ]

        for pattern in table_patterns:
            match = re.search(pattern, step_text, re.IGNORECASE)
            if match:
                details["table"] = match.group(1)
                break

        # Extract database name
        db_patterns = [
            r"\bUSE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*[a-zA-Z_][a-zA-Z0-9_]*",  # db.table
        ]

        for pattern in db_patterns:
            match = re.search(pattern, step_text, re.IGNORECASE)
            if match:
                details["database"] = match.group(1)
                break

        # Extract host/connection string
        host_patterns = [
            r"jdbc:[a-z]+://([^/\s]+)",
            r"mongodb://([^/\s]+)",
            r"postgresql://([^/\s]+)",
            r"mysql://([^/\s]+)",
            r"host[=:\s]+['\"]?([^'\";\\s]+)",
        ]

        for pattern in host_patterns:
            match = re.search(pattern, step_text, re.IGNORECASE)
            if match:
                details["host"] = match.group(1)
                break

        return details
