import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING, Dict

from karate_graph_analyzer.models import (
    Dependency,
    DependencyType,
    Examples,
    FeatureAST,
    GherkinTable,
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
from karate_graph_analyzer.parser.extractors.java_extractor import JavaExtractor

if TYPE_CHECKING:
    from karate_graph_analyzer.interfaces import IDependencyExtractor

logger = logging.getLogger(__name__)


@dataclass
class ParsingContext:
    """Internal state for FeatureFileParser."""
    file_path: str
    feature_name: Optional[str] = None
    background_steps: List[Step] = field(default_factory=list)
    scenarios: List[Scenario] = field(default_factory=list)
    feature_tags: List[str] = field(default_factory=list)
    current_tags: List[str] = field(default_factory=list)
    current_scenario: Optional[Scenario] = None
    current_examples: Optional[Examples] = None
    last_step: Optional[Step] = None
    state: str = "INIT"


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
            self.orchestrator.register_extractor(JavaExtractor())

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
        
        ctx = ParsingContext(file_path=file_path)

        for token in tokens:
            if self._handle_multiline_step(token, ctx):
                continue
            
            self._process_token(token, ctx)

        self._log_parse_warnings(ctx.scenarios)
        return FeatureAST(file_path, ctx.feature_name, ctx.scenarios, ctx.background_steps)

    def _handle_multiline_step(self, token, ctx) -> bool:
        """Handle steps that span multiple lines due to unclosed parentheses."""
        if (
            token.type not in [GherkinTokenType.STEP, GherkinTokenType.TABLE_ROW]
            and ctx.last_step is not None
            and self._has_unclosed_parentheses(ctx.last_step.text)
        ):
            ctx.last_step.text = f"{ctx.last_step.text}\n{token.text}"
            if not self._has_unclosed_parentheses(ctx.last_step.text):
                ctx.last_step = None
            return True
        return False

    def _process_token(self, token, ctx):
        """Dispatch token processing to specific handlers."""
        handlers = {
            GherkinTokenType.TAG: self._handle_tag,
            GherkinTokenType.FEATURE: self._handle_feature,
            GherkinTokenType.BACKGROUND: self._handle_background,
            GherkinTokenType.SCENARIO: self._handle_scenario,
            GherkinTokenType.SCENARIO_OUTLINE: self._handle_scenario,
            GherkinTokenType.STEP: self._handle_step,
            GherkinTokenType.EXAMPLES: self._handle_examples,
            GherkinTokenType.TABLE_ROW: self._handle_table_row
        }
        handler = handlers.get(token.type)
        if handler:
            handler(token, ctx)

    def _handle_tag(self, token, ctx):
        if token.line_number == 1:
            return
        tags = re.findall(r"@[\w\-_:]+", token.text)
        ctx.current_tags.extend(tags)
        ctx.current_examples = None
        ctx.last_step = None

    def _handle_feature(self, token, ctx):
        ctx.feature_name = token.text
        ctx.feature_tags = list(ctx.current_tags)
        ctx.current_tags = []
        ctx.current_examples = None
        ctx.last_step = None

    def _handle_background(self, token, ctx):
        ctx.state = "BACKGROUND"
        ctx.current_examples = None
        ctx.last_step = None

    def _handle_scenario(self, token, ctx):
        ctx.state = "SCENARIO"
        ctx.current_examples = None
        ctx.last_step = None
        
        merged_tags = list(set(ctx.feature_tags + ctx.current_tags))
        jira_tags = self._filter_jira_tags(merged_tags)
        
        setup_name = None
        setup_line = None
        if token.type == GherkinTokenType.SCENARIO_OUTLINE and ctx.scenarios:
            last_s = ctx.scenarios[-1]
            if "@setup" in last_s.tags:
                setup_name = last_s.name
                setup_line = last_s.line_number

        ctx.current_scenario = Scenario(
            name=token.text or f"Unnamed Scenario at {token.line_number}",
            type=ScenarioType.SCENARIO if token.type == GherkinTokenType.SCENARIO else ScenarioType.SCENARIO_OUTLINE,
            tags=merged_tags,
            jira_tags=jira_tags,
            file_path=ctx.file_path,
            line_number=token.line_number,
            steps=[],
            examples=None,
            setup_scenario=setup_name,
            setup_line_number=setup_line
        )
        ctx.scenarios.append(ctx.current_scenario)
        ctx.current_tags = []

    def _handle_step(self, token, ctx):
        step = Step(keyword=token.keyword, text=token.text, line_number=token.line_number)
        if ctx.state == "BACKGROUND":
            ctx.background_steps.append(step)
            ctx.last_step = step
        elif ctx.state == "SCENARIO" and ctx.current_scenario:
            ctx.current_scenario.steps.append(step)
            ctx.last_step = step
        ctx.current_examples = None

    def _handle_examples(self, token, ctx):
        if ctx.current_scenario:
            ctx.current_examples = Examples(table=GherkinTable(headers=[], rows=[]), line_number=token.line_number)
            ctx.current_scenario.examples = ctx.current_examples
            ctx.last_step = None

    def _handle_table_row(self, token, ctx):
        if ctx.current_examples:
            cells = self._parse_table_row(token.text)
            if not ctx.current_examples.table.headers:
                ctx.current_examples.table.headers = cells
            else:
                ctx.current_examples.table.rows.append(cells)

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
            if scenario.examples is not None and not scenario.examples.table.headers:
                logger.warning(
                    "Examples block for scenario '%s' has no table data", scenario.name
                )
            if scenario.examples is not None and scenario.examples.table.headers:
                expected_cols = len(scenario.examples.table.headers)
                for row in scenario.examples.table.rows:
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
        from karate_graph_analyzer.parser.extractors.java_extractor import JavaExtractor
        api_extractor = self.orchestrator.get_extractor_by_type(ApiExtractor)
        java_extractor = self.orchestrator.get_extractor_by_type(JavaExtractor)
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
            
            # 1.1 Local Java Aliases
            if java_extractor:
                java_extractor.extract_local_aliases(step.text)

        # 2. Finalize API dependencies
        dependencies.extend(tracker.finalize(scenario.line_number, scenario, http_method))
        
        # 2.1 Finalize Java dependencies
        if java_extractor:
            # Merge global aliases from config with local ones
            all_java_aliases = self.config.java_aliases.copy()
            all_java_aliases.update(java_extractor.local_aliases)
            
            used_java_classes = java_extractor.extract_java_usages(scenario, all_java_aliases)
            for java_class in used_java_classes:
                dependencies.append(Dependency(
                    type=DependencyType.JAVA,
                    target=java_class,
                    line_number=scenario.line_number,
                    parameters={
                        "class_path": java_class,
                        "scenario_name": scenario.name,
                        "scenario_tags": scenario.tags
                    }
                ))

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
