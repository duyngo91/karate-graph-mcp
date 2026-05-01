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
    """Extracts call read() dependencies from step text.

    Handles both single-line and multi-line call read() statements.
    Supports:
    - Quoted literals: call read('path/to/file.feature')
    - Variables: call read(PaymentServices + '@AddPayment')
    - Nested objects: call read(servies.t24.payment + '@AddPayment')
    - Concatenation: call read(webPages + 'LoginPage.feature')
    - Scenario tags: @AddPayment, @login
    """

    def __init__(self, config: ParserConfig) -> None:
        """Initialize with parser configuration.

        Args:
            config: Parser configuration for variable resolution and page directories
        """
        self.config = config

        # Compile patterns once for performance
        # Matches: call read('...'), callonce read('...'), karate.call('...'), karate.call(true, '...'), karate.callSingle('...')
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
        """Check if step contains a call read() or karate.call() statement."""
        return bool(re.search(r"(?:call|callonce)\s+read|karate\.call", step_text, re.IGNORECASE))

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        """Extract call read() dependencies from step text.

        Args:
            step_text: The text of a Gherkin step
            line_number: Line number in the feature file

        Returns:
            List of extracted dependencies
        """
        return self._extract_call_read_dependencies(step_text, line_number, validate_paths=False)

    def extract_with_validation(
        self, step_text: str, line_number: int, validate_paths: bool = False
    ) -> List[Dependency]:
        """Extract with optional path validation.

        Args:
            step_text: The text of a Gherkin step
            line_number: Line number in the feature file
            validate_paths: If True, log warnings for unresolved references

        Returns:
            List of extracted dependencies
        """
        return self._extract_call_read_dependencies(step_text, line_number, validate_paths)

    def _extract_call_read_dependencies(
        self, step_text: str, line_number: int, validate_paths: bool = False
    ) -> List[Dependency]:
        """Extract call read() dependencies from step text.

        Args:
            step_text: The step text to extract dependencies from
            line_number: The line number of the step
            validate_paths: If True, log warnings for unresolved references

        Returns:
            List of dependencies (includes unresolved references for graceful degradation)
        """
        dependencies: List[Dependency] = []

        # Try quoted pattern first
        quoted_matches = list(self._quoted_pattern.finditer(step_text))
        if quoted_matches:
            for match in quoted_matches:
                expression = match.group(1)
                params_str = match.group(2).strip() if match.group(2) else ""

                # Resolve expression (handles @tag extraction)
                resolved_path, scenario_tag = self._resolve_variable_expression(expression)

                # Determine dependency type based on resolved path
                dep_type = self._classify_call_dependency(resolved_path)

                # Check if path contains unresolved variables
                has_variables = "${" in resolved_path or "#(" in resolved_path

                # Log warning for unresolved references if validation is enabled
                if validate_paths and not has_variables:
                    if not resolved_path or resolved_path.isspace():
                        logger.warning(
                            f"Empty or whitespace-only path in call read() at line {line_number}"
                        )

                # Build parameters
                dep_params: Dict = {}
                if params_str:
                    dep_params["params"] = params_str
                if scenario_tag:
                    dep_params["scenario_tag"] = scenario_tag
                if has_variables:
                    dep_params["unresolved"] = True
                    dep_params["reason"] = "contains_variables"

                dependencies.append(
                    Dependency(
                        type=dep_type,
                        target=resolved_path,
                        line_number=line_number,
                        parameters=dep_params,
                    )
                )
        else:
            # Try variable pattern
            variable_matches = list(self._variable_pattern.finditer(step_text))
            for match in variable_matches:
                expression = match.group(1).strip()

                # Skip if this looks like a quoted string (shouldn't happen, but safety check)
                if expression.startswith(("'", '"')):
                    continue

                # Resolve expression (handles concatenation, nested paths, @tag)
                resolved_path, scenario_tag = self._resolve_variable_expression(expression)

                # Determine dependency type based on resolved path
                dep_type = self._classify_call_dependency(resolved_path)

                # Check if path contains unresolved variables
                has_variables = "${" in resolved_path or "#(" in resolved_path

                # Build parameters
                dep_params = {}
                if scenario_tag:
                    dep_params["scenario_tag"] = scenario_tag
                if has_variables:
                    dep_params["unresolved"] = True
                    dep_params["reason"] = "contains_variables"

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
        """Classify a call read() dependency as workflow, common, locator, or page object."""
        path_lower = path.lower()

        # Check if path matches locator directories
        locator_dirs = getattr(self.config, "locator_directories", ["locators", "resources/locators"])
        for loc_dir in locator_dirs:
            if loc_dir.lower() in path_lower:
                return DependencyType.LOCATOR

        # Check if path matches page object directories
        for page_dir in self.config.page_object_directories:
            if page_dir.lower() in path_lower:
                return DependencyType.PAGE
                
        # Check if path matches common API definition directories
        common_dirs = getattr(self.config, "common_directories", ["common", "services"])
        for common_dir in common_dirs:
            if common_dir.lower() in path_lower:
                print(f"DEBUG CLASSIFY: {path_lower} matched COMMON via {common_dir}")
                return DependencyType.COMMON

        print(f"DEBUG CLASSIFY: {path_lower} defaulted to WORKFLOW")
        # Default to workflow
        return DependencyType.WORKFLOW

    def _resolve_variable_expression(self, expression: str) -> Tuple[str, Optional[str]]:
        """Resolve variable expression including nested object paths and concatenation.

        Supports:
        - Simple variables: PaymentServices
        - Concatenation: webPages + 'LoginPage.feature'
        - Nested object paths: servies.t24.payment
        - Scenario tags: @AddPayment (extracted separately)
        - Quoted literals: 'classpath:common/services/...'

        Args:
            expression: Variable expression from call read()

        Returns:
            Tuple of (resolved_path, scenario_tag)
        """
        expression = expression.strip()
        scenario_tag = None

        # Extract scenario tag if present (e.g., '@AddPayment')
        if "@" in expression:
            # Split by @ to separate path and tag
            parts = expression.split("@", 1)
            expression = parts[0].strip()
            scenario_tag = parts[1].strip().strip("\"'")

        # Handle concatenation (e.g., "webPages + 'LoginPage.feature'")
        if "+" in expression:
            parts = expression.split("+")
            resolved_parts = []

            for part in parts:
                part = part.strip().strip("\"'")

                # Try to resolve as variable (including nested paths)
                resolved = self._resolve_single_variable(part)
                resolved_parts.append(resolved)

            resolved_path = "".join(resolved_parts)
        else:
            # Single expression (variable or literal)
            expression = expression.strip("\"'")
            resolved_path = self._resolve_single_variable(expression)

        # Normalize path separators (backslash → forward slash)
        resolved_path = resolved_path.replace("\\", "/")

        # Remove classpath: prefix if present
        if resolved_path.startswith("classpath:"):
            resolved_path = resolved_path[10:]  # len('classpath:') = 10

        return resolved_path, scenario_tag

    def _resolve_single_variable(self, var_expression: str) -> str:
        """Resolve a single variable expression (no concatenation).

        Supports:
        - Simple variables: PaymentServices
        - Nested object paths: servies.t24.payment
        - Literals: 'common/services/...'

        Args:
            var_expression: Variable expression (already stripped of quotes)

        Returns:
            Resolved path or original if not found
        """
        var_expression = var_expression.strip()

        # If it's a literal path (contains / or \\), return as-is
        if "/" in var_expression or "\\" in var_expression:
            return var_expression

        # Try direct match first (for simple variables and flattened nested paths)
        if var_expression in self.config.variable_patterns:
            return self.config.variable_patterns[var_expression]

        # Try nested resolution (e.g., 'servies.t24.payment')
        if "." in var_expression:
            # Check if flattened version exists in config
            if var_expression in self.config.variable_patterns:
                return self.config.variable_patterns[var_expression]

        # Not found, return original
        return var_expression
