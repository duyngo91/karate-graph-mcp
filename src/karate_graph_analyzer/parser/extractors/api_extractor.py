"""
API dependency extractor.

Strategy Pattern implementation for extracting HTTP API call
dependencies from Karate step text.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from karate_graph_analyzer.interfaces import IDependencyExtractor
from karate_graph_analyzer.models import Dependency, DependencyType, ParserConfig, Step

logger = logging.getLogger(__name__)


class ApiExtractor(IDependencyExtractor):
    """Extracts API call dependencies from step text.

    Handles:
    - Explicit URL strings: url 'http://example.com/api'
    - Variable references: baseUrl + '/endpoint'
    - Variable-only references: url apiEndpoint
    - Path statements: path '/api/users'
    - Combined url + path to create full endpoint
    - Resolves baseUrl using config mapping
    """

    def __init__(self, config: ParserConfig) -> None:
        """Initialize with parser configuration.

        Args:
            config: Parser configuration with API extraction rules and URL mappings
        """
        self.config = config

        # Pre-compile API extraction rule patterns
        self._api_rule_patterns = [
            re.compile(rule, re.IGNORECASE) for rule in self.config.api_extraction_rules
        ]

        # Pre-compile additional patterns
        self._var_url_pattern = re.compile(
            r"\burl\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", re.IGNORECASE
        )
        self._path_pattern = re.compile(
            r"\bpath\s+['\"]([^'\"]+)['\"]\b", re.IGNORECASE
        )

    def can_extract(self, step_text: str) -> bool:
        """Check if step contains API-related keywords."""
        step_lower = step_text.lower()
        return any(
            keyword in step_lower
            for keyword in ["url ", "url\t", "path ", "path\t"]
        )

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        """Extract API dependencies from step text.

        Args:
            step_text: The text of a Gherkin step
            line_number: Line number in the feature file

        Returns:
            List of extracted API dependencies
        """
        return self._extract_api_dependencies(step_text, line_number)

    def extract_http_method(self, steps: List[Step]) -> Optional[str]:
        """Extract HTTP method from scenario steps.

        Looks for 'When method get/post/put/delete/patch' pattern.
        Also detects dynamic methods like 'method __arg.method'.

        Args:
            steps: List of scenario steps

        Returns:
            HTTP method in uppercase (GET, POST, PUT, DELETE, PATCH, DYNAMIC) or None
        """
        # Pattern for static methods: method GET/POST/etc
        method_pattern = re.compile(
            r"\bmethod\s+(get|post|put|delete|patch)\b", re.IGNORECASE
        )

        # Pattern for dynamic methods: method __arg.xxx or method variable
        dynamic_pattern = re.compile(
            r"\bmethod\s+(__arg\.\w+|\w+(?!\s*\())", re.IGNORECASE
        )

        for step in steps:
            # Try static method first
            match = method_pattern.search(step.text)
            if match:
                return match.group(1).upper()

            # Try dynamic method
            match = dynamic_pattern.search(step.text)
            if match:
                # Check if it's a dynamic reference (starts with __arg or is a variable)
                method_value = match.group(1)
                if method_value.startswith("__arg") or method_value.upper() not in [
                    "GET",
                    "POST",
                    "PUT",
                    "DELETE",
                    "PATCH",
                ]:
                    return "DYNAMIC"

        return None

    def detect_dynamic_params(self, path: str) -> Tuple[str, List[str]]:
        """Detect and replace dynamic parameters in API path.

        Converts specific IDs to generic placeholders:
        - /api/products/PROD-001 → /api/products/{id}
        - /api/orders/ORD-123/items/ITEM-456 → /api/orders/{orderId}/items/{itemId}

        Args:
            path: API path (e.g., '/api/products/PROD-001')

        Returns:
            Tuple of (template_path, examples)
            - template_path: Path with {param} placeholders
            - examples: List of original values found
        """
        examples: List[str] = []

        # Patterns for common ID formats
        id_patterns = [
            (r"/([A-Z]+-\d+)", "/{id}"),  # PROD-001, ORD-123
            (r"/([a-z]+-\d+)", "/{id}"),  # prod-001, ord-123
            (r"/(\d+)", "/{id}"),  # 123, 456
            (
                r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                "/{id}",
            ),  # UUID
        ]

        template = path

        for pattern, replacement in id_patterns:
            matches = re.findall(pattern, template)
            if matches:
                examples.extend(matches)
                # Replace all occurrences
                template = re.sub(pattern, replacement, template)

        return template, examples

    def _extract_api_dependencies(
        self, step_text: str, line_number: int
    ) -> List[Dependency]:
        """Extract API call dependencies from step text."""
        dependencies: List[Dependency] = []

        # Use configured API extraction rules
        for pattern in self._api_rule_patterns:
            for match in pattern.finditer(step_text):
                endpoint = match.group(1)
                dependencies.append(
                    Dependency(
                        type=DependencyType.API,
                        target=endpoint,
                        line_number=line_number,
                        parameters={},
                    )
                )

        # Additional pattern for variable-only references
        for match in self._var_url_pattern.finditer(step_text):
            var_name = match.group(1)

            # Try to resolve variable from config base_url_mapping
            resolved_url = self.config.base_url_mapping.get(
                var_name
            ) or self.config.base_url_mapping.get(f"${{{var_name}}}")

            if resolved_url:
                # Use resolved URL instead of variable
                if not any(dep.target == resolved_url for dep in dependencies):
                    dependencies.append(
                        Dependency(
                            type=DependencyType.API,
                            target=resolved_url,
                            line_number=line_number,
                            parameters={"resolved_from": var_name},
                        )
                    )
            else:
                # Fallback: keep variable reference (unresolved)
                if not any(dep.target == f"${{{var_name}}}" for dep in dependencies):
                    dependencies.append(
                        Dependency(
                            type=DependencyType.API,
                            target=f"${{{var_name}}}",
                            line_number=line_number,
                            parameters={"variable": var_name, "unresolved": True},
                        )
                    )

        # Extract path statements (e.g., "path '/api/users'")
        for match in self._path_pattern.finditer(step_text):
            api_path = match.group(1)
            # Only add if it's not already captured
            if not any(dep.target == api_path for dep in dependencies):
                dependencies.append(
                    Dependency(
                        type=DependencyType.API,
                        target=api_path,
                        line_number=line_number,
                        parameters={"path_only": True},
                    )
                )

        return dependencies
