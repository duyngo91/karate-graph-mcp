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
        prefix_pattern = r"(?:(?:(?:call|callonce)\s+)?read|karate\.call(?:Single)?)\s*\(\s*(?:(?:true|false)\s*,\s*)?"
        
        self._quoted_pattern = re.compile(
            prefix_pattern + r"['\"]([^'\"]+)['\"](?:\s*,\s*(.+?))?\s*\)",
            re.IGNORECASE | re.DOTALL,
        )
        self._variable_pattern = re.compile(
            prefix_pattern + r"([^'\")\s][^)]*?)\s*\)(?:\s*\{[^}]*\})?",
            re.IGNORECASE | re.DOTALL,
        )

    def can_extract(self, step_text: str) -> bool:
        return bool(re.search(r"(?:(?:call|callonce)\s+)?read|karate\.call", step_text, re.IGNORECASE))

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
            
            resolved_path, scenario_tag, logical_path = self._resolve_variable_expression(expression)
            dep_type = self._classify_call_dependency(resolved_path)
            dependencies.append(
                self._build_call_dependency(
                    dep_type,
                    expression,
                    resolved_path,
                    logical_path,
                    scenario_tag,
                    line_number,
                    params_str=params_str,
                )
            )

        # 2. Variable patterns (if no quoted matches)
        if not dependencies:
            for match in self._variable_pattern.finditer(step_text):
                expression = match.group(1).strip()
                if expression.startswith(("'", '"')): continue
                
                resolved_path, scenario_tag, logical_path = self._resolve_variable_expression(expression)
                dep_type = self._classify_call_dependency(resolved_path)
                dependencies.append(
                    self._build_call_dependency(
                        dep_type,
                        expression,
                        resolved_path,
                        logical_path,
                        scenario_tag,
                        line_number,
                    )
                )

        return dependencies

    def _build_call_dependency(
        self,
        dep_type: DependencyType,
        expression: str,
        resolved_path: str,
        logical_path: Optional[str],
        scenario_tag: Optional[str],
        line_number: int,
        params_str: str = "",
    ) -> Dependency:
        dep_params = self._build_resolution_params(resolved_path)
        if params_str:
            dep_params["params"] = params_str
        if scenario_tag:
            dep_params["scenario_tag"] = scenario_tag

        return Dependency(
            type=dep_type,
            target=logical_path or resolved_path,
            line_number=line_number,
            parameters={
                **dep_params,
                "original_expression": expression,
                "physical_path": resolved_path if logical_path else None,
                "scenario_tag": scenario_tag,
            },
        )

    def _classify_call_dependency(self, path: str) -> DependencyType:
        path_lower = path.lower()
        
        # 1. Detect Data files
        if any(path_lower.endswith(ext) for ext in ['.json', '.csv', '.yaml', '.yml']):
            return DependencyType.DATA
            
        # 2. Detect by directory
        path_parts = [p.lower() for p in path.replace("\\", "/").split("/")[:-1]]
        
        if any(d.lower() in path_parts for d in getattr(self.config, "locator_directories", ["locators"])):
            return DependencyType.LOCATOR
        if any(d.lower() in path_parts for d in self.config.page_object_directories):
            return DependencyType.PAGE
        if any(d.lower() in path_parts for d in getattr(self.config, "common_directories", ["common", "services"])):
            return DependencyType.COMMON
            
        return DependencyType.WORKFLOW

    def _build_resolution_params(self, path: str) -> dict:
        """Mark dynamic call targets so callers can degrade gracefully."""
        if "${" in path:
            return {"unresolved": True, "reason": "contains_variables"}
        if "#(" in path:
            return {"unresolved": True, "reason": "contains_karate_expression"}
        return {}

    def _resolve_variable_expression(self, expression: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Resolve a dynamic Karate expression into a path and scenario tag."""
        # 1. Handle concat: var + '@tag' or var + 'path'
        concat_match = re.search(r"([\w\.]+)\s*\+\s*['\"]([^'\"]+)['\"]", expression)
        if concat_match:
            var_name = concat_match.group(1)
            suffix = concat_match.group(2)
            
            base_path = self.config.variable_patterns.get(var_name)
            if base_path:
                full_path = base_path + suffix
                scenario_tag = None
                logical_path = None
                
                # Check if suffix is a tag
                if suffix.startswith('@'):
                    return base_path, suffix, None
                
                # Check if full_path has a tag
                if "@" in full_path:
                    parts = full_path.split("@", 1)
                    return parts[0], "@" + parts[1], None
                    
                return full_path, None, None

        expression = expression.strip()
        scenario_tag = None
        logical_path = None

        # Handle cases like: read(var '@tag') or read(var, '@tag')
        if "@" in expression:
            match = re.search(r"['\"]?@([\w\-_]+)['\"]?\s*$", expression)
            if match:
                scenario_tag = match.group(1)
                expression = expression[:match.start()].strip().rstrip(",")
            else:
                parts = expression.split("@", 1)
                expression = parts[0].strip()
                scenario_tag = parts[1].strip().strip("\"'")

        if "+" in expression:
            parts = [p.strip() for p in expression.split("+")]
            resolved_parts = []
            logical_parts = []
            has_variable = False
            
            for p in parts:
                raw = p.strip("\"'")
                # Check if it's a known variable from config
                res = self.config.variable_patterns.get(raw)
                if res and not p.startswith(("'","\"")):
                    resolved_parts.append(res)
                    logical_parts.append(f"${{{raw}}}")
                    has_variable = True
                else:
                    resolved_parts.append(raw)
                    logical_parts.append(raw)
            
            resolved_path = "".join(resolved_parts)
            if has_variable:
                logical_path = "".join(logical_parts)
        else:
            first_arg = expression.split(",")[0].strip().strip("\"'")
            resolved_path = self.config.variable_patterns.get(first_arg, first_arg)
            if first_arg in self.config.variable_patterns and not expression.strip().startswith(("'","\"")):
                logical_path = f"${{{first_arg}}}"

        # Normalize separators BEFORE stripping prefixes
        resolved_path = resolved_path.replace("\\", "/")
        
        # If it's a classpath: path, keep it relative to resources
        if resolved_path.startswith("classpath:"):
            resolved_path = resolved_path.replace("classpath:", "").lstrip("/")
            
        return resolved_path, scenario_tag, logical_path

    def _resolve_single_variable(self, var_expression: str) -> str:
        var_expression = var_expression.strip()
        if "/" in var_expression or "\\" in var_expression:
            return var_expression
            
        # Logical Logic: If it's a known variable like dataPath, 
        # we might want to keep the name for the graph ID but 
        # for now we return the resolved value to maintain path resolution.
        # The 'original_expression' parameter will help in logical merging.
        return self.config.variable_patterns.get(var_expression, var_expression)
