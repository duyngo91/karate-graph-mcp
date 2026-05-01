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
    - Path statements: path '/api/users'
    - Method markers: method GET
    - Dynamic params detection
    """

    def __init__(self, config: ParserConfig) -> None:
        self.config = config

        # Pre-compile API extraction rule patterns
        self._api_rule_patterns = [
            re.compile(rule, re.IGNORECASE) for rule in self.config.api_extraction_rules
        ]

        # Compile common patterns
        self._method_pattern = re.compile(
            r"\bmethod\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b", re.IGNORECASE
        )
        self._dynamic_method_pattern = re.compile(
            r"\bmethod\s+(__arg\.\w+|\w+(?!\s*\())", re.IGNORECASE
        )
        self._var_url_pattern = re.compile(
            r"\burl\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", re.IGNORECASE
        )
        self._path_pattern = re.compile(
            r"\bpath\s+['\"]([^'\"]+)['\"]", re.IGNORECASE
        )

    def can_extract(self, step_text: str) -> bool:
        step_lower = step_text.lower()
        return any(
            keyword in step_lower
            for keyword in ["url", "path", "method"]
        )

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        dependencies: List[Dependency] = []

        # 1. Extract HTTP Methods (METHOD_MARKER)
        for match in self._method_pattern.finditer(step_text):
            method = match.group(1).upper()
            dependencies.append(
                Dependency(
                    type=DependencyType.API,
                    target="METHOD_MARKER",
                    line_number=line_number,
                    parameters={"http_method": method}
                )
            )

        # 2. Use configured API extraction rules (URL/BaseURL)
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

        # 3. Variable-only references
        for match in self._var_url_pattern.finditer(step_text):
            var_name = match.group(1)
            resolved_url = self.config.base_url_mapping.get(var_name) or \
                           self.config.base_url_mapping.get(f"${{{var_name}}}")

            if resolved_url:
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
                if not any(dep.target == f"${{{var_name}}}" for dep in dependencies):
                    dependencies.append(
                        Dependency(
                            type=DependencyType.API,
                            target=f"${{{var_name}}}",
                            line_number=line_number,
                            parameters={"variable": var_name, "unresolved": True},
                        )
                    )

        # 4. Extract path statements
        for match in self._path_pattern.finditer(step_text):
            api_path = match.group(1)
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

    def extract_http_method(self, steps: List[Step]) -> Optional[str]:
        """Extract HTTP method from scenario steps."""
        for step in steps:
            # Try static method first
            match = self._method_pattern.search(step.text)
            if match:
                return match.group(1).upper()

            # Try dynamic method
            match = self._dynamic_method_pattern.search(step.text)
            if match:
                method_value = match.group(1)
                if method_value.startswith('__arg') or \
                   method_value.upper() not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                    return "DYNAMIC"
        
        return None

    def detect_dynamic_params(self, path: str) -> Tuple[str, List[str]]:
        """Detect and replace dynamic parameters in API path."""
        examples = []
        id_patterns = [
            (r'/([A-Z]+-\d+)', '/{id}'),  # PROD-001
            (r'/([a-z]+-\d+)', '/{id}'),  # prod-001
            (r'/(\d+)', '/{id}'),          # 123
            (r'/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', '/{id}'),  # UUID
        ]
        
        template = path
        for pattern, replacement in id_patterns:
            matches = re.findall(pattern, template)
            if matches:
                examples.extend(matches)
                template = re.sub(pattern, replacement, template)
        
        return template, examples
