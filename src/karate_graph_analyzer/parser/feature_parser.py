"""
Feature file parser implementation.

Parses Karate feature files into structured AST representation.
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from karate_graph_analyzer.models import (
    Dependency,
    DependencyType,
    Examples,
    FeatureAST,
    ParseError,
    ParserConfig,
    PathContext,
    Scenario,
    ScenarioType,
    Step,
)

# Set up logger for unresolved references
logger = logging.getLogger(__name__)


class FeatureFileParser:
    """Parses Karate feature files into structured AST."""

    def __init__(self, config: ParserConfig = ParserConfig()) -> None:
        """Initialize parser with configuration for syntax variations.

        Args:
            config: Parser configuration for handling syntax variations
        """
        self.config = config
        
        # Compile regex patterns for performance
        self._feature_pattern = re.compile(r"^\s*Feature:\s*(.+)$", re.IGNORECASE)
        self._background_pattern = re.compile(r"^\s*Background:\s*$", re.IGNORECASE)
        self._scenario_pattern = re.compile(r"^\s*Scenario:\s*(.+)$", re.IGNORECASE)
        self._scenario_outline_pattern = re.compile(
            r"^\s*Scenario Outline:\s*(.+)$", re.IGNORECASE
        )
        self._examples_pattern = re.compile(r"^\s*Examples:\s*$", re.IGNORECASE)
        self._step_pattern = re.compile(
            r"^\s*(Given|When|Then|And|But|\*)\s+(.+)$", re.IGNORECASE
        )
        self._tag_pattern = re.compile(r"@[\w\-_]+")
        
        # Compile Jira tag patterns from config
        self._jira_patterns = [re.compile(pattern) for pattern in self.config.jira_tag_patterns]

    def parse_file(self, file_path: str) -> FeatureAST:
        """Parse a single feature file.

        Args:
            file_path: Path to the feature file to parse

        Returns:
            FeatureAST with scenarios, tags, dependencies

        Raises:
            ParseError: If file is malformed
        """
        # Validate file exists
        if not os.path.exists(file_path):
            raise ParseError(
                file_path=file_path,
                line_number=None,
                message=f"Feature file not found: {file_path}",
                error_code="1002",
            )
        
        # Read file content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError as e:
            raise ParseError(
                file_path=file_path,
                line_number=None,
                message=f"Invalid file encoding: {str(e)}",
                error_code="1004",
            )
        except IOError as e:
            raise ParseError(
                file_path=file_path,
                line_number=None,
                message=f"Unable to read file: {str(e)}",
                error_code="1003",
            )
        
        # Parse content
        try:
            feature_name = self._extract_feature_name(lines)
            background_steps = self._extract_background(lines)
            scenarios = self._extract_scenarios_from_lines(lines, file_path)
            
            return FeatureAST(
                file_path=file_path,
                feature_name=feature_name,
                scenarios=scenarios,
                background_steps=background_steps,
            )
        except ParseError:
            raise
        except Exception as e:
            raise ParseError(
                file_path=file_path,
                line_number=None,
                message=f"Malformed feature file: {str(e)}",
                error_code="1001",
            )

    def extract_scenarios(self, ast: FeatureAST) -> List[Scenario]:
        """Extract all Scenario and Scenario Outline definitions.

        Args:
            ast: Parsed feature AST

        Returns:
            List of all scenarios in the feature file
        """
        return ast.scenarios

    def extract_dependencies(self, scenario: Scenario, validate_paths: bool = False) -> List[Dependency]:
        """Extract call read(), API calls, page objects, DB operations.

        Args:
            scenario: Scenario to extract dependencies from
            validate_paths: If True, validate that referenced files exist (default: False for graceful degradation)

        Returns:
            List of dependencies found in the scenario
        """
        dependencies: List[Dependency] = []
        
        # Track baseUrl and paths to combine them
        base_url = None
        api_paths = []
        
        # Process all steps (scenario steps only - background is handled separately)
        for step in scenario.steps:
            step_text = step.text
            
            # Extract call read() dependencies (workflows/page objects)
            call_deps = self._extract_call_read_dependencies(step_text, step.line_number, validate_paths)
            dependencies.extend(call_deps)
            
            # Extract API dependencies
            api_deps = self._extract_api_dependencies(step_text, step.line_number)
            
            # Separate baseUrl from paths
            for api_dep in api_deps:
                if api_dep.parameters.get("path_only"):
                    api_paths.append(api_dep)
                elif api_dep.parameters.get("resolved_from"):
                    # This is a resolved baseUrl
                    base_url = api_dep
                elif "${" in api_dep.target or "baseUrl" in api_dep.target.lower():
                    # This is an unresolved baseUrl
                    base_url = api_dep
                else:
                    # This is a complete URL, add directly
                    dependencies.append(api_dep)
            
            # Extract database dependencies
            db_deps = self._extract_database_dependencies(step_text, step.line_number)
            dependencies.extend(db_deps)
        
        # Combine baseUrl with paths to create full endpoints
        if base_url and api_paths:
            # We have both baseUrl and paths - combine them
            for path_dep in api_paths:
                # Create combined endpoint (full URL)
                combined_target = f"{base_url.target}{path_dep.target}"
                combined_dep = Dependency(
                    type=DependencyType.API,
                    target=combined_target,
                    line_number=path_dep.line_number,
                    parameters={
                        "base_url": base_url.target,
                        "path": path_dep.target,
                        "combined": True
                    }
                )
                dependencies.append(combined_dep)
            # Don't add base_url separately - it's already part of combined URLs
        elif base_url and not api_paths:
            # Only baseUrl, no paths - add it
            dependencies.append(base_url)
        elif api_paths and not base_url:
            # Only paths, no baseUrl - add them as-is
            for path_dep in api_paths:
                dependencies.append(path_dep)
        
        return dependencies
    
    def extract_dependencies_with_background(
        self, 
        scenario: Scenario, 
        background_steps: List[Step],
        validate_paths: bool = False
    ) -> List[Dependency]:
        """Extract dependencies including background steps.
        
        This method processes both background and scenario steps to properly
        combine baseUrl from background with paths from scenario.
        Also extracts HTTP method to create proper endpoint names.
        
        Args:
            scenario: Scenario to extract dependencies from
            background_steps: Background steps from the feature file
            validate_paths: If True, validate that referenced files exist
        
        Returns:
            List of dependencies found in background + scenario
        """
        dependencies: List[Dependency] = []
        
        # Track baseUrl and paths to combine them
        base_url = None
        api_paths = []
        
        # Extract HTTP method from scenario steps
        http_method = self._extract_http_method(scenario.steps)
        
        # Process background steps first (to get baseUrl)
        for step in background_steps:
            step_text = step.text
            
            # Extract API dependencies from background
            api_deps = self._extract_api_dependencies(step_text, step.line_number)
            
            for api_dep in api_deps:
                if api_dep.parameters.get("resolved_from"):
                    # This is a resolved baseUrl
                    base_url = api_dep
                elif "${" in api_dep.target or "baseUrl" in api_dep.target.lower():
                    # This is an unresolved baseUrl
                    base_url = api_dep
        
        # Process scenario steps
        for step in scenario.steps:
            step_text = step.text
            
            # Extract call read() dependencies (workflows/page objects)
            call_deps = self._extract_call_read_dependencies(step_text, step.line_number, validate_paths)
            dependencies.extend(call_deps)
            
            # Extract API dependencies
            api_deps = self._extract_api_dependencies(step_text, step.line_number)
            
            # Separate baseUrl from paths
            for api_dep in api_deps:
                if api_dep.parameters.get("path_only"):
                    api_paths.append(api_dep)
                elif api_dep.parameters.get("resolved_from"):
                    # Override baseUrl if found in scenario
                    base_url = api_dep
                elif "${" in api_dep.target or "baseUrl" in api_dep.target.lower():
                    # Override baseUrl if found in scenario
                    base_url = api_dep
                else:
                    # This is a complete URL, add directly with method
                    if http_method:
                        api_dep.parameters["http_method"] = http_method
                    dependencies.append(api_dep)
            
            # Extract database dependencies
            db_deps = self._extract_database_dependencies(step_text, step.line_number)
            dependencies.extend(db_deps)
        
        # Combine baseUrl with paths to create full endpoints
        if base_url and api_paths:
            # We have both baseUrl and paths - combine them
            for path_dep in api_paths:
                # Create combined endpoint (full URL)
                combined_target = f"{base_url.target}{path_dep.target}"
                
                # Detect dynamic params and create template
                template_path, examples = self._detect_dynamic_params(path_dep.target)
                
                combined_dep = Dependency(
                    type=DependencyType.API,
                    target=combined_target,
                    line_number=path_dep.line_number,
                    parameters={
                        "base_url": base_url.target,
                        "path": path_dep.target,
                        "path_template": template_path,
                        "http_method": http_method,
                        "examples": examples,
                        "combined": True
                    }
                )
                dependencies.append(combined_dep)
            # Don't add base_url separately - it's already part of combined URLs
        elif base_url and not api_paths:
            # Only baseUrl, no paths - add it with method
            if http_method:
                base_url.parameters["http_method"] = http_method
            dependencies.append(base_url)
        elif api_paths and not base_url:
            # Only paths, no baseUrl - add them as-is with method
            for path_dep in api_paths:
                if http_method:
                    path_dep.parameters["http_method"] = http_method
                # Detect dynamic params
                template_path, examples = self._detect_dynamic_params(path_dep.target)
                path_dep.parameters["path_template"] = template_path
                path_dep.parameters["examples"] = examples
                dependencies.append(path_dep)
        
        return dependencies

    def resolve_path(self, call_statement: str, context: PathContext) -> str:
        """Resolve relative paths and variable expressions.
        
        Handles:
        - Variable substitution using configured patterns
        - Relative path resolution from current file directory
        - Fallback to project root resolution
        - Absolute path pass-through

        Args:
            call_statement: The call read() statement to resolve
            context: Path resolution context with current file, project root, and config

        Returns:
            Resolved absolute or relative path
        """
        # Extract path from call read() statement
        path_match = re.search(
            r"call\s+read\s*\(\s*['\"]([^'\"]+)['\"]", 
            call_statement, 
            re.IGNORECASE | re.DOTALL
        )
        if not path_match:
            return call_statement
        
        path = path_match.group(1)
        
        # Resolve variable expressions using configured patterns
        for var_name, var_value in context.parser_config.variable_patterns.items():
            path = path.replace(var_name, var_value)
        
        # If path is absolute, return as-is
        if os.path.isabs(path):
            return path
        
        # Resolve relative to current file's directory
        current_dir = os.path.dirname(context.current_file_path)
        resolved = os.path.normpath(os.path.join(current_dir, path))
        
        # If resolved path doesn't exist, try relative to project root
        if not os.path.exists(resolved) and context.project_root:
            resolved_from_root = os.path.normpath(os.path.join(context.project_root, path))
            if os.path.exists(resolved_from_root):
                resolved = resolved_from_root
        
        return resolved

    def _extract_feature_name(self, lines: List[str]) -> Optional[str]:
        """Extract feature name from lines."""
        for line in lines:
            match = self._feature_pattern.match(line)
            if match:
                return match.group(1).strip()
        return None

    def _extract_background(self, lines: List[str]) -> List[Step]:
        """Extract background steps from lines."""
        background_steps: List[Step] = []
        in_background = False
        
        for line_num, line in enumerate(lines, start=1):
            # Check if we're entering background
            if self._background_pattern.match(line):
                in_background = True
                continue
            
            # Check if we're leaving background (entering scenario)
            if in_background and (
                self._scenario_pattern.match(line) or self._scenario_outline_pattern.match(line)
            ):
                break
            
            # Extract steps if in background
            if in_background:
                step_match = self._step_pattern.match(line)
                if step_match:
                    background_steps.append(
                        Step(
                            keyword=step_match.group(1),
                            text=step_match.group(2).strip(),
                            line_number=line_num,
                        )
                    )
        
        return background_steps

    def _extract_scenarios_from_lines(self, lines: List[str], file_path: str) -> List[Scenario]:
        """Extract all scenarios from file lines."""
        scenarios: List[Scenario] = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            line_num = i + 1
            
            # Check for Scenario or Scenario Outline
            scenario_match = self._scenario_pattern.match(line)
            outline_match = self._scenario_outline_pattern.match(line)
            
            if scenario_match or outline_match:
                try:
                    # Extract tags from previous lines
                    tags, jira_tags = self._extract_tags_before_line(lines, i)
                    
                    # Determine scenario type and name
                    if scenario_match:
                        scenario_type = ScenarioType.SCENARIO
                        name = scenario_match.group(1).strip()
                    else:
                        scenario_type = ScenarioType.SCENARIO_OUTLINE
                        name = outline_match.group(1).strip()
                    
                    # Validate scenario name is not empty
                    if not name:
                        logger.warning(
                            f"{file_path}:{line_num}: Scenario has empty name, using placeholder"
                        )
                        name = f"Unnamed Scenario at line {line_num}"
                    
                    # Extract steps and examples
                    steps, examples, next_i = self._extract_steps_and_examples(
                        lines, i + 1, scenario_type
                    )
                    
                    # Validate Scenario Outline has Examples
                    if scenario_type == ScenarioType.SCENARIO_OUTLINE and examples is None:
                        logger.warning(
                            f"{file_path}:{line_num}: Scenario Outline '{name}' has no Examples block"
                        )
                    
                    # Create scenario
                    scenario = Scenario(
                        name=name,
                        type=scenario_type,
                        tags=tags,
                        jira_tags=jira_tags,
                        file_path=file_path,
                        line_number=line_num,
                        steps=steps,
                        examples=examples,
                    )
                    scenarios.append(scenario)
                    
                    i = next_i
                except Exception as e:
                    # Log error but continue parsing (graceful degradation)
                    logger.error(
                        f"{file_path}:{line_num}: Error parsing scenario: {str(e)}"
                    )
                    # Skip to next line and continue
                    i += 1
            else:
                i += 1
        
        return scenarios

    def _extract_tags_before_line(self, lines: List[str], line_index: int) -> Tuple[List[str], List[str]]:
        """Extract tags from lines before the given line index."""
        all_tags: List[str] = []
        jira_tags: List[str] = []
        
        # Look backwards for tag lines
        i = line_index - 1
        while i >= 0:
            line = lines[i].strip()
            
            # Stop if we hit a non-tag, non-empty line
            if line and not line.startswith("@"):
                break
            
            # Extract tags from this line
            if line.startswith("@"):
                tags = self._tag_pattern.findall(line)
                all_tags.extend(tags)
            
            i -= 1
        
        # Reverse to maintain original order
        all_tags.reverse()
        
        # Identify Jira tags using configured patterns
        for tag in all_tags:
            for jira_pattern in self._jira_patterns:
                if jira_pattern.match(tag):
                    jira_tags.append(tag)
                    break
        
        return all_tags, jira_tags

    def _extract_steps_and_examples(
        self, lines: List[str], start_index: int, scenario_type: ScenarioType
    ) -> Tuple[List[Step], Optional[Examples], int]:
        """Extract steps and examples block from lines.
        
        Handles multi-line steps by detecting unclosed parentheses and
        combining continuation lines.
        """
        steps: List[Step] = []
        examples: Optional[Examples] = None
        i = start_index
        
        while i < len(lines):
            line = lines[i]
            line_num = i + 1
            
            # Check if we've hit another scenario
            if self._scenario_pattern.match(line) or self._scenario_outline_pattern.match(line):
                break
            
            # Check for Examples block (only for Scenario Outline)
            if scenario_type == ScenarioType.SCENARIO_OUTLINE and self._examples_pattern.match(line):
                examples, i = self._extract_examples_block(lines, i + 1, line_num)
                continue
            
            # Extract step
            step_match = self._step_pattern.match(line)
            if step_match:
                keyword = step_match.group(1)
                step_text = step_match.group(2).strip()
                
                # Check if this is a multi-line statement (unclosed parentheses)
                if self._has_unclosed_parentheses(step_text):
                    # Combine with following lines until parentheses are balanced
                    combined_text, next_i = self._combine_multiline_step(lines, i, step_text)
                    step_text = combined_text
                    i = next_i
                
                steps.append(
                    Step(
                        keyword=keyword,
                        text=step_text,
                        line_number=line_num,
                    )
                )
            
            i += 1
        
        return steps, examples, i

    def _has_unclosed_parentheses(self, text: str) -> bool:
        """Check if text has unclosed parentheses."""
        open_count = text.count('(')
        close_count = text.count(')')
        return open_count > close_count

    def _combine_multiline_step(self, lines: List[str], start_index: int, initial_text: str) -> Tuple[str, int]:
        """Combine multi-line step text until parentheses are balanced.
        
        Returns:
            Tuple of (combined_text, last_line_index)
        """
        combined = initial_text
        i = start_index + 1
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Stop if we hit a new step or scenario
            if (self._step_pattern.match(lines[i]) or 
                self._scenario_pattern.match(lines[i]) or 
                self._scenario_outline_pattern.match(lines[i])):
                break
            
            # Add the line to combined text
            if line:
                combined += " " + line
            
            # Check if parentheses are now balanced
            if not self._has_unclosed_parentheses(combined):
                break
            
            i += 1
        
        return combined, i

    def _extract_examples_block(
        self, lines: List[str], start_index: int, examples_line_num: int
    ) -> Tuple[Examples, int]:
        """Extract Examples block with headers and rows.
        
        Handles malformed Examples blocks gracefully by logging warnings.
        """
        headers: List[str] = []
        rows: List[List[str]] = []
        i = start_index
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Stop if we hit another scenario or examples
            if (
                self._scenario_pattern.match(line)
                or self._scenario_outline_pattern.match(line)
                or self._examples_pattern.match(line)
            ):
                break
            
            # Parse table rows
            if line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line.split("|")[1:-1]]
                
                if not headers:
                    headers = cells
                    # Validate headers are not empty
                    if not headers or all(not h for h in headers):
                        logger.warning(
                            f"Line {i + 1}: Examples block has empty headers"
                        )
                else:
                    # Validate row has same number of columns as headers
                    if len(cells) != len(headers):
                        logger.warning(
                            f"Line {i + 1}: Examples row has {len(cells)} columns but headers have {len(headers)}"
                        )
                    rows.append(cells)
            
            i += 1
        
        # Validate Examples block has at least headers
        if not headers:
            logger.warning(
                f"Line {examples_line_num}: Examples block has no table data"
            )
        
        return Examples(headers=headers, rows=rows, line_number=examples_line_num), i

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
        if '@' in expression:
            # Split by @ to separate path and tag
            parts = expression.split('@', 1)
            expression = parts[0].strip()
            scenario_tag = parts[1].strip().strip('"\'')
        
        # Handle concatenation (e.g., "webPages + 'LoginPage.feature'")
        if '+' in expression:
            parts = expression.split('+')
            resolved_parts = []
            
            for part in parts:
                part = part.strip().strip('"\'')
                
                # Try to resolve as variable (including nested paths)
                resolved = self._resolve_single_variable(part)
                resolved_parts.append(resolved)
            
            resolved_path = ''.join(resolved_parts)
        else:
            # Single expression (variable or literal)
            expression = expression.strip('"\'')
            resolved_path = self._resolve_single_variable(expression)
        
        # Normalize path separators (backslash → forward slash)
        resolved_path = resolved_path.replace('\\', '/')
        
        # Remove classpath: prefix if present
        if resolved_path.startswith('classpath:'):
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
        
        # If it's a literal path (contains / or \), return as-is
        if '/' in var_expression or '\\' in var_expression:
            return var_expression
        
        # Try direct match first (for simple variables and flattened nested paths)
        if var_expression in self.config.variable_patterns:
            return self.config.variable_patterns[var_expression]
        
        # Try nested resolution (e.g., 'servies.t24.payment')
        if '.' in var_expression:
            # Check if flattened version exists in config
            if var_expression in self.config.variable_patterns:
                return self.config.variable_patterns[var_expression]
            
            # Try to resolve from nested config structure
            # This would require config to support nested dicts
            # For now, we rely on flattened keys in config
            # Example config:
            # {
            #   "servies.t24.payment": "common/services/t24/payment/PaymentServices.feature"
            # }
        
        # Not found, return original
        return var_expression
    
    def _extract_call_read_dependencies(self, step_text: str, line_number: int, validate_paths: bool = False) -> List[Dependency]:
        """Extract call read() dependencies from step text.
        
        Handles both single-line and multi-line call read() statements.
        Supports:
        - Quoted literals: call read('path/to/file.feature')
        - Variables: call read(PaymentServices + '@AddPayment')
        - Nested objects: call read(servies.t24.payment + '@AddPayment')
        - Concatenation: call read(webPages + 'LoginPage.feature')
        - Scenario tags: @AddPayment, @login
        
        Examples:
            - call read('path/to/file.feature')
            - call read('path/to/file.feature@AddPayment')
            - call read(PaymentServices + '@AddPayment') {... body}
            - call read(servies.t24.payment + '@AddPayment') {... body}
            - call read(webPages + 'LoginPage.feature@login')
        
        Args:
            step_text: The step text to extract dependencies from
            line_number: The line number of the step
            validate_paths: If True, log warnings for unresolved references
        
        Returns:
            List of dependencies (includes unresolved references for graceful degradation)
        """
        dependencies: List[Dependency] = []
        
        # Pattern 1: Quoted literals - call read('path') or call read("path")
        quoted_pattern = re.compile(
            r"call\s+read\s*\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*(.+?))?\s*\)",
            re.IGNORECASE | re.DOTALL,
        )
        
        # Pattern 2: Variable expressions - call read(variable + 'suffix')
        # Matches: call read(anything_without_quotes)
        variable_pattern = re.compile(
            r"call\s+read\s*\(\s*([^'\")\s][^)]*?)\s*\)(?:\s*\{[^}]*\})?",
            re.IGNORECASE | re.DOTALL,
        )
        
        # Try quoted pattern first
        quoted_matches = list(quoted_pattern.finditer(step_text))
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
                dep_params = {}
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
            variable_matches = list(variable_pattern.finditer(step_text))
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
        """Classify a call read() dependency as workflow or page object."""
        path_lower = path.lower()
        
        # Check if path matches page object directories
        for page_dir in self.config.page_object_directories:
            if page_dir.lower() in path_lower:
                return DependencyType.PAGE
        
        # Default to workflow
        return DependencyType.WORKFLOW

    def _extract_api_dependencies(self, step_text: str, line_number: int) -> List[Dependency]:
        """Extract API call dependencies from step text.
        
        Handles:
        - Explicit URL strings: url 'http://example.com/api'
        - Variable references: baseUrl + '/endpoint'
        - Variable-only references: url apiEndpoint
        - Path statements: path '/api/users'
        - Combined url + path to create full endpoint
        - Resolves baseUrl using config mapping
        """
        dependencies: List[Dependency] = []
        
        # Use configured API extraction rules
        for rule in self.config.api_extraction_rules:
            pattern = re.compile(rule, re.IGNORECASE)
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
        
        # Additional pattern for variable-only references (e.g., "url apiEndpoint" or "url baseUrl")
        # This catches cases where the URL is stored in a variable
        var_url_pattern = re.compile(r"\burl\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", re.IGNORECASE)
        for match in var_url_pattern.finditer(step_text):
            var_name = match.group(1)
            
            # Try to resolve variable from config base_url_mapping
            # Check both plain name and ${name} format
            resolved_url = self.config.base_url_mapping.get(var_name) or \
                           self.config.base_url_mapping.get(f"${{{var_name}}}")
            
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
        path_pattern = re.compile(r"\bpath\s+['\"]([^'\"]+)['\"]", re.IGNORECASE)
        for match in path_pattern.finditer(step_text):
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

    def _extract_http_method(self, steps: List[Step]) -> Optional[str]:
        """Extract HTTP method from scenario steps.
        
        Looks for 'When method get/post/put/delete/patch' pattern.
        
        Args:
            steps: List of scenario steps
        
        Returns:
            HTTP method in uppercase (GET, POST, PUT, DELETE, PATCH) or None
        """
        method_pattern = re.compile(r"\bmethod\s+(get|post|put|delete|patch)\b", re.IGNORECASE)
        
        for step in steps:
            match = method_pattern.search(step.text)
            if match:
                return match.group(1).upper()
        
        return None
    
    def _detect_dynamic_params(self, path: str) -> Tuple[str, List[str]]:
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
        examples = []
        
        # Patterns for common ID formats
        id_patterns = [
            (r'/([A-Z]+-\d+)', '/{id}'),  # PROD-001, ORD-123
            (r'/([a-z]+-\d+)', '/{id}'),  # prod-001, ord-123
            (r'/(\d+)', '/{id}'),          # 123, 456
            (r'/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', '/{id}'),  # UUID
        ]
        
        template = path
        
        for pattern, replacement in id_patterns:
            matches = re.findall(pattern, template)
            if matches:
                examples.extend(matches)
                # Replace all occurrences
                template = re.sub(pattern, replacement, template)
        
        return template, examples

    def _extract_database_dependencies(self, step_text: str, line_number: int) -> List[Dependency]:
        """Extract database operation dependencies from step text.
        
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
        dependencies: List[Dependency] = []
        
        # Common database keywords and patterns
        db_keywords = [
            r"\bSELECT\b",
            r"\bINSERT\b",
            r"\bUPDATE\b",
            r"\bDELETE\b",
            r"\bCREATE\b",
            r"\bDROP\b",
            r"\bALTER\b",
            r"\bTRUNCATE\b",
            r"\bdb\s*\.",
            r"\bdatabase\s*\.",
        ]
        
        for keyword in db_keywords:
            if re.search(keyword, step_text, re.IGNORECASE):
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
        details = {}
        
        # Extract operation type (first SQL keyword found)
        operations = ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE"]
        for op in operations:
            if re.search(rf"\b{op}\b", step_text, re.IGNORECASE):
                details["operation"] = op
                break
        
        # Extract table name from SQL statements
        # Pattern: FROM table_name, INTO table_name, UPDATE table_name, etc.
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
        # Pattern: database.table or USE database
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
        # Pattern: jdbc:mysql://host:port/db, mongodb://host:port/db, etc.
        host_patterns = [
            r"jdbc:[a-z]+://([^/\s]+)",
            r"mongodb://([^/\s]+)",
            r"postgresql://([^/\s]+)",
            r"mysql://([^/\s]+)",
            r"host[=:\s]+['\"]?([^'\";\s]+)",
        ]
        
        for pattern in host_patterns:
            match = re.search(pattern, step_text, re.IGNORECASE)
            if match:
                details["host"] = match.group(1)
                break
        
        return details
