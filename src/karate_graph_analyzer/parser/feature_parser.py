import logging
import os
import re
from typing import List, Optional, TYPE_CHECKING

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
from karate_graph_analyzer.parser.lexer import GherkinLexer, GherkinTokenType
from karate_graph_analyzer.parser.orchestrator import DependencyOrchestrator
from karate_graph_analyzer.utils.path_resolver import PathResolver
from karate_graph_analyzer.parser.api_context_tracker import ApiContextTracker

if TYPE_CHECKING:
    from karate_graph_analyzer.interfaces import IDependencyExtractor

logger = logging.getLogger(__name__)


class FeatureFileParser:
    """Parses Karate feature files using Lexer/Orchestrator architecture.
    
    This class acts as a Facade and Orchestrator for the parsing subsystem.
    """

    def __init__(
        self,
        config: ParserConfig = ParserConfig(),
        extractors: Optional[List["IDependencyExtractor"]] = None,
    ) -> None:
        self.config = config
        self.lexer = GherkinLexer()
        self.orchestrator = DependencyOrchestrator(config)

        if extractors:
            for ex in extractors:
                self.orchestrator.register_extractor(ex)
        else:
            from karate_graph_analyzer.parser.extractors.api_extractor import ApiExtractor
            from karate_graph_analyzer.parser.extractors.call_read_extractor import CallReadExtractor
            from karate_graph_analyzer.parser.extractors.database_extractor import DatabaseExtractor
            
            self.orchestrator.register_extractor(CallReadExtractor(config))
            self.orchestrator.register_extractor(ApiExtractor(config))
            self.orchestrator.register_extractor(DatabaseExtractor(config))

    def parse_file(self, file_path: str) -> FeatureAST:
        """Parse a single feature file into a structured AST representation."""
        if not os.path.exists(file_path):
            raise ParseError(file_path, None, f"Feature file not found: {file_path}", "1002")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError as e:
            raise ParseError(file_path, None, f"Invalid file encoding: {str(e)}", "1004")
        except Exception as e:
            raise ParseError(file_path, None, f"Unable to read file: {str(e)}", "1003")

        tokens = list(self.lexer.tokenize(lines))
        
        feature_name = None
        background_steps = []
        scenarios = []
        
        feature_tags = []
        current_tags = []
        current_scenario = None
        current_examples = None
        last_step = None
        state = "INIT" # INIT, BACKGROUND, SCENARIO

        for token in tokens:
            if (
                token.type not in [GherkinTokenType.STEP, GherkinTokenType.TABLE_ROW]
                and last_step is not None
                and self._has_unclosed_parentheses(last_step.text)
            ):
                last_step.text = f"{last_step.text}\n{token.text}"
                if not self._has_unclosed_parentheses(last_step.text):
                    last_step = None
                continue

            if token.type == GherkinTokenType.TAG:
                # Extract tags from the @line (including colons for ALM2/ID tags)
                tags = re.findall(r"@[\w\-_:]+", token.text)
                current_tags.extend(tags)
                current_examples = None
                last_step = None
            
            elif token.type == GherkinTokenType.FEATURE:
                feature_name = token.text
                feature_tags = list(current_tags) # Store feature level tags
                current_tags = [] # Reset for potential background or first scenario
                current_examples = None
                last_step = None
            
            elif token.type == GherkinTokenType.BACKGROUND:
                state = "BACKGROUND"
                current_examples = None
                last_step = None
            
            elif token.type in [GherkinTokenType.SCENARIO, GherkinTokenType.SCENARIO_OUTLINE]:
                state = "SCENARIO"
                current_examples = None
                last_step = None
                
                # Merge feature tags with scenario tags
                merged_tags = list(set(feature_tags + current_tags))
                
                jira_tags = self._filter_jira_tags(merged_tags)
                
                # Check for @setup linkage
                setup_name = None
                setup_line = None
                if token.type == GherkinTokenType.SCENARIO_OUTLINE and scenarios:
                    last_s = scenarios[-1]
                    if "@setup" in last_s.tags:
                        setup_name = last_s.name
                        setup_line = last_s.line_number

                current_scenario = Scenario(
                    name=token.text or f"Unnamed Scenario at {token.line_number}",
                    type=ScenarioType.SCENARIO if token.type == GherkinTokenType.SCENARIO else ScenarioType.SCENARIO_OUTLINE,
                    tags=merged_tags,
                    jira_tags=jira_tags,
                    file_path=file_path,
                    line_number=token.line_number,
                    steps=[],
                    examples=None,
                    setup_scenario=setup_name,
                    setup_line_number=setup_line
                )
                scenarios.append(current_scenario)
                current_tags = [] # Reset for next scenario
            
            elif token.type == GherkinTokenType.STEP:
                step = Step(keyword=token.keyword, text=token.text, line_number=token.line_number)
                if state == "BACKGROUND":
                    background_steps.append(step)
                    last_step = step
                elif state == "SCENARIO" and current_scenario:
                    current_scenario.steps.append(step)
                    last_step = step
                current_examples = None
            
            elif token.type == GherkinTokenType.EXAMPLES and current_scenario:
                current_examples = Examples(headers=[], rows=[], line_number=token.line_number)
                current_scenario.examples = current_examples
                last_step = None

            elif token.type == GherkinTokenType.TABLE_ROW and current_examples:
                cells = self._parse_table_row(token.text)
                if not current_examples.headers:
                    current_examples.headers = cells
                else:
                    current_examples.rows.append(cells)

        self._log_parse_warnings(scenarios)
        return FeatureAST(file_path, feature_name, scenarios, background_steps)

    def extract_scenarios(self, ast: FeatureAST) -> List[Scenario]:
        """Return scenarios from a parsed AST for backward compatibility."""
        return ast.scenarios

    def extract_dependencies(self, scenario: Scenario, validate_paths: bool = False) -> List[Dependency]:
        """Extract dependencies without background context for legacy callers."""
        return self.extract_dependencies_with_background(scenario, [], validate_paths=validate_paths)

    def _parse_table_row(self, row: str) -> List[str]:
        """Parse a Gherkin table row while preserving empty cells."""
        stripped = row.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        return [cell.strip() for cell in stripped.split("|")]

    def _has_unclosed_parentheses(self, text: str) -> bool:
        """Detect simple multi-line Karate calls such as call read(...)."""
        return text.count("(") > text.count(")")

    def _log_parse_warnings(self, scenarios: List[Scenario]) -> None:
        """Log non-fatal structure issues while preserving partial parse results."""
        for scenario in scenarios:
            if scenario.type == ScenarioType.SCENARIO_OUTLINE and scenario.examples is None:
                logger.warning(
                    "Scenario Outline '%s' has no Examples block", scenario.name
                )
            if scenario.examples is not None and not scenario.examples.headers:
                logger.warning(
                    "Examples block for scenario '%s' has no table data", scenario.name
                )
            if scenario.examples is not None and scenario.examples.headers:
                expected_cols = len(scenario.examples.headers)
                for row in scenario.examples.rows:
                    if len(row) != expected_cols:
                        logger.warning(
                            "Examples row in scenario '%s' has %d columns, expected %d",
                            scenario.name,
                            len(row),
                            expected_cols,
                        )

    def extract_dependencies_with_background(
        self, scenario: Scenario, background_steps: List[Step], validate_paths: bool = False
    ) -> List[Dependency]:
        """Orchestrate dependency extraction across steps, merging background context."""
        from karate_graph_analyzer.parser.extractors.api_extractor import ApiExtractor
        api_extractor = self.orchestrator.get_extractor_by_type(ApiExtractor)
        http_method = (api_extractor.extract_http_method(scenario.steps) if api_extractor else "GET") or "GET"

        # Resolve scoped config for this specific file
        original_mapping = self.config.base_url_mapping
        self.config.base_url_mapping = self.config.get_config_for_path(scenario.file_path)

        tracker = ApiContextTracker(api_extractor)
        dependencies: List[Dependency] = []
        
        # 1. Process ALL steps sequentially
        all_steps = background_steps + scenario.steps
        for step in all_steps:
            deps = self.orchestrator.extract_from_step(step.text, step.line_number)
            for d in deps:
                if not tracker.process_dependency(d, scenario, http_method):
                    # Non-API dependency
                    d.parameters.update({
                        "scenario_name": scenario.name,
                        "scenario_tags": scenario.tags
                    })
                    dependencies.append(d)

        # 2. Finalize API dependencies
        dependencies.extend(tracker.finalize(scenario.line_number, scenario, http_method))

        # 3. Add @setup dependency if present
        if scenario.setup_scenario:
            dependencies.append(Dependency(
                type=DependencyType.SETUP,
                target=scenario.setup_scenario,
                line_number=scenario.line_number,
                parameters={
                    "file_path": scenario.file_path,
                    "setup_line_number": scenario.setup_line_number
                }
            ))

        # 4. Final Deduplication
        unique_deps: List[Dependency] = []
        seen = set()
        for d in dependencies:
            # Key: type + target + line_number (as requested by user)
            key = (d.type, d.target, d.line_number)
            if key not in seen:
                if validate_paths and d.type in {
                    DependencyType.WORKFLOW,
                    DependencyType.COMMON,
                    DependencyType.PAGE,
                    DependencyType.LOCATOR,
                } and not d.target.strip():
                    logger.warning(
                        "Dependency target at line %s is empty or whitespace", d.line_number
                    )
                unique_deps.append(d)
                seen.add(key)
        
        # Restore original mapping
        self.config.base_url_mapping = original_mapping
        
        return unique_deps

    def resolve_path(self, call_statement: str, context: PathContext) -> str:
        """Resolve path using the specialized PathResolver utility."""
        return PathResolver.resolve(call_statement, context)

    def _filter_jira_tags(self, tags: List[str]) -> List[str]:
        """Extract Jira-related tags using configured patterns."""
        jira_patterns = [re.compile(p) for p in self.config.jira_tag_patterns]
        jira_tags = []
        for tag in tags:
            if any(p.match(tag) for p in jira_patterns):
                jira_tags.append(tag)
        return jira_tags
