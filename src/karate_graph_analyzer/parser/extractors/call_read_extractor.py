"""
Call read() dependency extractor.

Strategy Pattern implementation for extracting workflow and page object
dependencies from Karate call read() statements.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from karate_graph_analyzer.interfaces import IDependencyExtractor
from karate_graph_analyzer.models import Dependency, DependencyType, ParserConfig

logger = logging.getLogger(__name__)


class CallReadExtractor(IDependencyExtractor):
    """Extracts call read() dependencies from step text."""

    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        prefix_pattern = r"(?:(?:call|callonce)\s+read|karate\.call(?:Single)?)\s*\(\s*(?:(?:true|false)\s*,\s*)?"
        
        self._quoted_pattern = re.compile(
            prefix_pattern + r"['\"]([^'\"]+)['\"](?:\s*,\s*(.+?))?\s*\)",
            re.IGNORECASE | re.DOTALL,
        )
        self._variable_pattern = re.compile(
            prefix_pattern + r"([^'\")\s][^)]*?)\s*\)(?:\s*\{[^}]*\})?",
            re.IGNORECASE | re.DOTALL,
        )

    def can_extract(self, step_text: str) -> bool:
        return bool(re.search(r"(?:call|callonce)\s+read|karate\.call", step_text, re.IGNORECASE))

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        return self._extract_call_read_dependencies(step_text, line_number)

    def _extract_call_read_dependencies(
        self, step_text: str, line_number: int, validate_paths: bool = False
    ) -> List[Dependency]:
        dependencies: List[Dependency] = []

        # 1. Quoted patterns
        for match in self._quoted_pattern.finditer(step_text):
            expression = match.group(1)
            params_str = match.group(2).strip() if match.group(2) else ""
            
            resolved_path, scenario_tag = self._resolve_variable_expression(expression)
            dep_type = self._classify_call_dependency(resolved_path)
            
            dep_params = {}
            if params_str: dep_params["params"] = params_str
            if scenario_tag: dep_params["scenario_tag"] = scenario_tag
            
            dependencies.append(
                Dependency(
                    type=dep_type,
                    target=resolved_path,
                    line_number=line_number,
                    parameters=dep_params,
                )
            )

        # 2. Variable patterns (if no quoted matches)
        if not dependencies:
            for match in self._variable_pattern.finditer(step_text):
                expression = match.group(1).strip()
                if expression.startswith(("'", '"')): continue
                
                resolved_path, scenario_tag = self._resolve_variable_expression(expression)
                dep_type = self._classify_call_dependency(resolved_path)
                
                dep_params = {}
                if scenario_tag: dep_params["scenario_tag"] = scenario_tag
                
                dependencies.append(
                    Dependency(
                        type=dep_type,
                        target=resolved_path,
                        line_number=line_number,
                        parameters=dep_params,
                    )
                )

        return dependencies

    def _classify_call_dependency(self, path: str) -> DependencyType:
        path_lower = path.lower()
        
        if any(d.lower() in path_lower for d in getattr(self.config, "locator_directories", ["locators"])):
            return DependencyType.LOCATOR
        if any(d.lower() in path_lower for d in self.config.page_object_directories):
            return DependencyType.PAGE
        if any(d.lower() in path_lower for d in getattr(self.config, "common_directories", ["common", "services"])):
            return DependencyType.COMMON
            
        return DependencyType.WORKFLOW

    def _resolve_variable_expression(self, expression: str) -> Tuple[str, Optional[str]]:
        expression = expression.strip()
        scenario_tag = None

        # Handle cases like: read(var '@tag') or read(var, '@tag')
        # Check for @ outside of quotes or in a trailing string
        if "@" in expression:
            # Check if it's like: var '@tag'
            match = re.search(r"['\"]?@([\w\-_]+)['\"]?\s*$", expression)
            if match:
                scenario_tag = match.group(1)
                # Remove the tag part from expression
                expression = expression[:match.start()].strip().rstrip(",")
            else:
                # Fallback for standard @ separator
                parts = expression.split("@", 1)
                expression = parts[0].strip()
                scenario_tag = parts[1].strip().strip("\"'")

        if "+" in expression:
            parts = expression.split("+")
            resolved_path = "".join(self._resolve_single_variable(p.strip().strip("\"'")) for p in parts)
        else:
            # Also handle potential comma-separated arguments where the first is the variable
            first_arg = expression.split(",")[0].strip()
            resolved_path = self._resolve_single_variable(first_arg.strip("\"'"))

        resolved_path = resolved_path.replace("\\", "/")
        if resolved_path.startswith("classpath:"):
            resolved_path = resolved_path[10:]

        return resolved_path, scenario_tag

    def _resolve_single_variable(self, var_expression: str) -> str:
        var_expression = var_expression.strip()
        if "/" in var_expression or "\\" in var_expression:
            return var_expression
        return self.config.variable_patterns.get(var_expression, var_expression)
