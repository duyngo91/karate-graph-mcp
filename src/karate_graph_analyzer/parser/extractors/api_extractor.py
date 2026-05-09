"""
API dependency extractor.

Strategy Pattern implementation for extracting HTTP API call
dependencies from Karate step text.
"""

import logging
import re
from typing import List, Optional, Tuple

from karate_graph_analyzer.interfaces import IDependencyExtractor
from karate_graph_analyzer.models import Dependency, DependencyType, ParserConfig, Step

logger = logging.getLogger(__name__)


class ApiExtractor(IDependencyExtractor):
    """Extract API call dependencies from Karate step text."""

    NON_URL_VARIABLES = {"path", "method", "request", "response", "headers"}

    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        self._api_rule_patterns = [
            re.compile(rule, re.IGNORECASE) for rule in self.config.api_extraction_rules
        ]
        self._method_pattern = re.compile(
            r"\bmethod\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b", re.IGNORECASE
        )
        self._dynamic_method_pattern = re.compile(
            r"\bmethod\s+(__arg\.\w+|\w+(?!\s*\())", re.IGNORECASE
        )
        self._var_url_pattern = re.compile(
            r"\burl\s+(['\"]([^'\"]+)['\"]\s*\+\s*)?([a-zA-Z_][a-zA-Z0-9_\.]*)\b",
            re.IGNORECASE,
        )
        self._path_pattern = re.compile(
            r"\bpath\s+['\"]([^'\"]+)['\"]", re.IGNORECASE
        )

    def can_extract(self, step_text: str) -> bool:
        step_lower = step_text.lower()
        return any(keyword in step_lower for keyword in ["url", "path", "method"])

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        dependencies: List[Dependency] = []
        dependencies.extend(self._extract_method_markers(step_text, line_number))
        dependencies.extend(self._extract_rule_urls(step_text, line_number))
        dependencies.extend(self._extract_variable_urls(step_text, line_number, dependencies))
        dependencies.extend(self._extract_path_statements(step_text, line_number, dependencies))
        return dependencies

    def _extract_method_markers(self, step_text: str, line_number: int) -> List[Dependency]:
        return [
            Dependency(
                type=DependencyType.API,
                target="METHOD_MARKER",
                line_number=line_number,
                parameters={"http_method": match.group(1).upper()},
            )
            for match in self._method_pattern.finditer(step_text)
        ]

    def _extract_rule_urls(self, step_text: str, line_number: int) -> List[Dependency]:
        dependencies: List[Dependency] = []
        for pattern in self._api_rule_patterns:
            for match in pattern.finditer(step_text):
                dependency = self._build_rule_url_dependency(match.group(1), line_number)
                if dependency:
                    dependencies.append(dependency)
        return dependencies

    def _build_rule_url_dependency(
        self, endpoint: str, line_number: int
    ) -> Optional[Dependency]:
        sanitized_endpoint = self.sanitize_url(endpoint)
        if not sanitized_endpoint:
            return None

        logical_endpoint = self.normalize_logical_url(sanitized_endpoint)
        target_endpoint = (
            sanitized_endpoint
            if sanitized_endpoint.startswith(("http://", "https://"))
            else logical_endpoint
        )
        return Dependency(
            type=DependencyType.API,
            target=target_endpoint,
            line_number=line_number,
            parameters={
                "physical_url": (
                    sanitized_endpoint if logical_endpoint != sanitized_endpoint else None
                ),
                "logical_url": (
                    logical_endpoint if logical_endpoint != sanitized_endpoint else None
                ),
            },
        )

    def _extract_variable_urls(
        self,
        step_text: str,
        line_number: int,
        existing_dependencies: List[Dependency],
    ) -> List[Dependency]:
        dependencies: List[Dependency] = []
        for match in self._var_url_pattern.finditer(step_text):
            prefix_val = match.group(2)
            var_name = match.group(3)
            if var_name.lower() in self.NON_URL_VARIABLES:
                continue

            dependency = self._build_variable_url_dependency(var_name, prefix_val, line_number)
            if not self._has_dependency_target(
                existing_dependencies + dependencies, dependency.target
            ):
                dependencies.append(dependency)
        return dependencies

    def _build_variable_url_dependency(
        self,
        var_name: str,
        prefix_val: Optional[str],
        line_number: int,
    ) -> Dependency:
        resolved_url = self.config.base_url_mapping.get(var_name) or self.config.base_url_mapping.get(
            f"${{{var_name}}}"
        )
        if resolved_url:
            return self._build_resolved_variable_url_dependency(
                var_name, str(resolved_url), prefix_val, line_number
            )
        return self._build_unresolved_variable_url_dependency(var_name, prefix_val, line_number)

    def _build_resolved_variable_url_dependency(
        self,
        var_name: str,
        resolved_url: str,
        prefix_val: Optional[str],
        line_number: int,
    ) -> Dependency:
        full_val = f"{prefix_val}{resolved_url}" if prefix_val else resolved_url
        logical_endpoint = self.normalize_logical_url(full_val)
        return Dependency(
            type=DependencyType.API,
            target=logical_endpoint,
            line_number=line_number,
            parameters={
                "resolved_from": var_name,
                "prefix": prefix_val,
                "physical_url": full_val if logical_endpoint != full_val else None,
            },
        )

    def _build_unresolved_variable_url_dependency(
        self,
        var_name: str,
        prefix_val: Optional[str],
        line_number: int,
    ) -> Dependency:
        target = f"${{{var_name}}}"
        if prefix_val:
            target = f"{prefix_val}{target}"
        return Dependency(
            type=DependencyType.API,
            target=target,
            line_number=line_number,
            parameters={
                "variable": var_name,
                "prefix": prefix_val,
                "unresolved": True,
            },
        )

    def _extract_path_statements(
        self,
        step_text: str,
        line_number: int,
        existing_dependencies: List[Dependency],
    ) -> List[Dependency]:
        dependencies: List[Dependency] = []
        for match in self._path_pattern.finditer(step_text):
            sanitized_path = self.sanitize_url(match.group(1))
            if sanitized_path and not self._has_dependency_target(
                existing_dependencies + dependencies, sanitized_path
            ):
                dependencies.append(
                    Dependency(
                        type=DependencyType.API,
                        target=sanitized_path,
                        line_number=line_number,
                        parameters={"path_only": True},
                    )
                )
        return dependencies

    def _has_dependency_target(self, dependencies: List[Dependency], target: str) -> bool:
        return any(dep.target == target for dep in dependencies)

    def sanitize_url(self, url: str) -> Optional[str]:
        """Filter out code snippets and keep endpoint-like strings only."""
        if not url:
            return None

        logic_keywords = [
            "var ", "let ", "const ", "if (", "karate.log(", "return ", ";",
            "{", "}", "\n", "\r", "function", "=>", "(", ")", "||", "&&",
            "==", "!=", '"', "'", ",", "  ",
        ]
        if any(keyword in url for keyword in logic_keywords):
            return None
        if len(url) > 200:
            return None

        url = url.strip().strip('"').strip("'")
        if not re.match(r"^[a-zA-Z0-9_\-\.\/:@\$\{\}]+$", url):
            return None
        return url

    def normalize_logical_url(self, url: str) -> str:
        """Replace physical URLs with logical variable names if found in mapping."""
        clean_url = url.rstrip("/")
        direct_match = self.config.global_reverse_mapping.get(clean_url) or (
            self.config.global_reverse_mapping.get(url)
        )
        if direct_match:
            return f"${{{direct_match}}}"

        for physical_url, var_name in self._sorted_reverse_mapping():
            if not physical_url or len(physical_url) < 5:
                continue
            clean_physical = physical_url.rstrip("/")
            if clean_url == clean_physical:
                return f"${{{var_name}}}"
            if url.startswith(clean_physical + "/"):
                return url.replace(clean_physical, f"${{{var_name}}}")

        for var_name, base_url in self.config.base_url_mapping.items():
            if not base_url or len(str(base_url)) < 5:
                continue
            clean_base = str(base_url).rstrip("/")
            if clean_url == clean_base:
                return f"${{{var_name}}}"
            if url.startswith(clean_base + "/"):
                return url.replace(clean_base, f"${{{var_name}}}")

        return url

    def _sorted_reverse_mapping(self) -> List[Tuple[str, str]]:
        return sorted(
            self.config.global_reverse_mapping.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        )

    def extract_http_method(self, steps: List[Step]) -> Optional[str]:
        """Extract HTTP method from scenario steps."""
        for step in steps:
            match = self._method_pattern.search(step.text)
            if match:
                return match.group(1).upper()

            match = self._dynamic_method_pattern.search(step.text)
            if match:
                method_value = match.group(1)
                if method_value.startswith("__arg") or method_value.upper() not in [
                    "GET", "POST", "PUT", "DELETE", "PATCH"
                ]:
                    return "DYNAMIC"
        return None

    def detect_dynamic_params(self, path: str) -> Tuple[str, List[str]]:
        """Detect and replace dynamic parameters in API path."""
        examples = []
        id_patterns = [
            (r"/([A-Z]+-\d+)", "/{id}"),
            (r"/([a-z]+-\d+)", "/{id}"),
            (r"/(\d+)", "/{id}"),
            (
                r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
                "/{id}",
            ),
        ]

        template = path
        for pattern, replacement in id_patterns:
            matches = re.findall(pattern, template)
            if matches:
                examples.extend(matches)
                template = re.sub(pattern, replacement, template)
        return template, examples
