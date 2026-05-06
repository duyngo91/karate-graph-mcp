"""
Data models for the Karate Feature Graph Analyzer.

This module contains all dataclasses and enums representing the core domain models
as specified in the design document.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import re


@dataclass(frozen=True)
class ApiEndpoint:
    """Value object for API endpoints."""
    base_url: str
    path: str
    method: str = "GET"

    def __post_init__(self):
        # Normalize path
        if self.path.startswith("http"):
            # If path is actually a full URL, we might need to handle it differently
            pass

    @property
    def identity(self) -> str:
        """Unique identity for the endpoint."""
        return f"{self.method}:{self.base_url}/{self.path.lstrip('/')}"


@dataclass
class GherkinTable:
    """Value object for Gherkin tables."""
    headers: List[str]
    rows: List[List[str]]

    def get_row_dict(self, index: int) -> Dict[str, str]:
        if index >= len(self.rows):
            return {}
        return dict(zip(self.headers, self.rows[index]))


class ScenarioType(str, Enum):
    """Type of test scenario."""

    SCENARIO = "SCENARIO"
    SCENARIO_OUTLINE = "SCENARIO_OUTLINE"


class DependencyType(str, Enum):
    """Type of dependency relationship."""

    WORKFLOW = "WORKFLOW"
    COMMON = "COMMON"
    API = "API"
    PAGE = "PAGE"
    DATABASE = "DATABASE"
    LOCATOR = "LOCATOR"
    SETUP = "SETUP"
    DATA = "DATA"
    CONTAINS = "CONTAINS"


class NodeType(str, Enum):
    """Type of graph node."""

    TEST_CASE = "TEST_CASE"
    WORKFLOW = "WORKFLOW"
    COMMON = "COMMON"  # Common API definition
    SCENARIO = "SCENARIO"  # Workflow scenario (@AddPayment, @GetPayment)
    API = "API"
    API_GROUP = "API_GROUP"  # Hierarchical API grouping (domain, path segments)
    PAGE = "PAGE"
    ACTION = "ACTION"  # Page action (@login, @navigate)
    DATABASE = "DATABASE"
    LOCATOR = "LOCATOR"
    DATA = "DATA"
    FOLDER = "FOLDER"
    FILE = "FILE"


class FlowType(str, Enum):
    """Broad architectural flow category."""

    API = "API"
    UI = "UI"
    DATABASE = "DATABASE"
    TEST = "TEST"
    DATA = "DATA"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    UNKNOWN = "UNKNOWN"


class ComponentCategory(str, Enum):
    """Broad category for component classification."""

    BUSINESS = "BUSINESS"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    UNKNOWN = "UNKNOWN"


@dataclass
class Step:
    """Represents a single step in a scenario."""

    keyword: str  # Given, When, Then, And, But
    text: str
    line_number: int


@dataclass
class Examples:
    """Represents an Examples block in a Scenario Outline."""

    table: GherkinTable
    line_number: int


@dataclass
class Scenario:
    """Represents a test case (Scenario or Scenario Outline)."""

    name: str
    type: ScenarioType
    tags: List[str]
    jira_tags: List[str]
    file_path: str
    line_number: int
    steps: List[Step]
    examples: Optional[Examples] = None
    setup_scenario: Optional[str] = None  # Name of the @setup scenario for this outline
    setup_line_number: Optional[int] = None  # Line number of the @setup scenario


@dataclass
class Dependency:
    """Represents a dependency extracted from feature file."""

    type: DependencyType
    target: str  # File path, URL, or operation identifier
    line_number: int
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeMetadata:
    """Metadata associated with graph nodes."""

    file_path: Optional[str]
    line_number: Optional[int]
    jira_tags: List[str]
    project_name: str
    category: ComponentCategory = ComponentCategory.UNKNOWN
    flow: FlowType = FlowType.UNKNOWN
    environment_variants: Dict[str, str] = field(default_factory=dict)  # env -> Physical path/URL
    additional_data: Dict[str, Any] = field(default_factory=dict)
    execution_history: List[str] = field(default_factory=list) # List of "PASSED", "FAILED"
    expert_notes: List[Dict[str, Any]] = field(default_factory=list)
    suggestions: List[Dict[str, Any]] = field(default_factory=list)


class VisualizationMode(str, Enum):
    """Rendering modes for the graph visualizer."""

    DEFAULT = "DEFAULT"
    EXECUTION = "EXECUTION"
    DIFF = "DIFF"


class DiffStatus(str, Enum):
    """Status of a node/edge in a differential analysis."""

    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    UNCHANGED = "UNCHANGED"


@dataclass
class Node:
    """Graph node representing a test component."""

    id: str
    type: NodeType
    name: str
    metadata: NodeMetadata
    tags: List[str] = field(default_factory=list)
    
    # Execution status (Idea #1)
    execution_status: Optional[str] = None  # PASSED, FAILED, SKIPPED
    execution_details: Dict[str, Any] = field(default_factory=dict)
    
    # Diff status (Idea #2)
    diff_status: DiffStatus = DiffStatus.UNCHANGED


@dataclass
class Edge:
    """Directed edge representing dependency relationship."""

    id: str
    from_node: str
    to_node: str
    type: DependencyType
    line_number: Optional[int] = None
    diff_status: DiffStatus = DiffStatus.UNCHANGED


@dataclass
class DependencyGraph:
    """Complete dependency graph for a project."""

    project_name: str
    nodes: Dict[str, Node]
    edges: Dict[str, Edge]
    cycles: List[List[str]] = field(default_factory=list)
    config: Optional["ParserConfig"] = None

    def merge(self, other: "DependencyGraph", new_project_name: Optional[str] = None) -> "DependencyGraph":
        """Merge another graph into this one."""
        from karate_graph_analyzer.graph.core.graph_merger import DependencyGraphMerger
        merger = DependencyGraphMerger()
        return merger.merge(self, other, new_project_name)


@dataclass
class AffectedTestCase:
    """Test case affected by a change."""

    node_id: str
    name: str
    jira_tags: List[str]
    dependency_path: List[str]  # Path from test case to changed component
    depth: int
    line_number: Optional[int] = None  # Specific line causing the dependency


@dataclass
class ImpactResult:
    """Result of impact analysis."""

    changed_component: str
    affected_test_cases: List[AffectedTestCase]
    total_count: int


@dataclass
class ComponentInstance:
    """Specific instance of a reusable component."""

    project_name: str
    file_path: str
    node_id: str


@dataclass
class ReusableComponent:
    """Component used across multiple projects."""

    type: NodeType
    name: str
    usage_count: int
    instances: List[ComponentInstance]


@dataclass
class ParserConfig:
    """Configuration for parser to handle syntax variations."""

    jira_tag_patterns: List[str] = field(
        default_factory=lambda: [
            r"@[A-Za-z]+-\d+",      # @PROJ-123 (mixed case with hyphen)
            r"@[A-Za-z]+_\d+",      # @PROJ_123 (mixed case with underscore)
        ]
    )
    workflow_directories: List[str] = field(default_factory=lambda: ["workflow", "workflows"])
    common_directories: List[str] = field(default_factory=lambda: ["common", "services"])
    page_object_directories: List[str] = field(default_factory=lambda: ["pages", "webPages"])
    locator_directories: List[str] = field(default_factory=lambda: ["locators", "resources/locators"])
    variable_patterns: Dict[str, str] = field(default_factory=dict)
    base_url_mapping: Dict[str, str] = field(default_factory=dict)
    global_reverse_mapping: Dict[str, str] = field(default_factory=dict)  # physical -> logical
    api_extraction_rules: List[str] = field(
        default_factory=lambda: [
            r"url\s+['\"]([^'\"]+)['\"]",  # url 'http://...'
            r"url\s+['\"]([^'\"]+)['\"]\s*\+", # url 'http://...' + var
            r"url\s+[\w\.]+\s*\+\s*['\"]([^'\"]+)['\"]", # url baseUrl + '/endpoint'
            r"baseUrl\s*\+\s*['\"]([^'\"]+)['\"]",  # baseUrl + '/endpoint'
        ]
    )
    # Base URL resolution - maps variable names to actual URLs
    base_url_mapping: Dict[str, str] = field(
        default_factory=lambda: {
            "baseUrl": "https://api.example.com",  # Default value
            "${baseUrl}": "https://api.example.com",
        }
    )
    
    # Scoped URL mappings - maps directory paths to variable dictionaries
    scoped_url_mappings: Dict[str, Dict[str, str]] = field(default_factory=dict)

    # Multi-environment mapping - maps variable names to environment dictionary
    # e.g., "t24Url": {"sit": "https://sit.t24.com", "stg": "https://t24.com"}
    env_url_mapping: Dict[str, Dict[str, str]] = field(default_factory=dict)

    # Reverse mapping for logical name resolution (physical -> logical)
    global_reverse_mapping: Dict[str, str] = field(default_factory=dict)

    # Tags to ignore for node identification and display (regression/technical tags)
    metadata_tags: List[str] = field(
        default_factory=lambda: ["@healing", "@smoke", "@regression", "@ignore"]
    )
    metadata_tag_patterns: List[str] = field(
        default_factory=lambda: [r"^@ALM2:", r"^@TC-\d+", r"^@JiraId-"]
    )

    # Mapping keywords in file paths to Business Domains for visualization grouping
    domain_mapping: Dict[str, str] = field(
        default_factory=lambda: {
            'authentication': 'Authentication', 'auth': 'Authentication', 'login': 'Authentication',
            'orders': 'Order Management', 'order': 'Order Management',
            'products': 'Product Catalog', 'product': 'Product Catalog', 'catalog': 'Product Catalog',
            'users': 'User Management', 'user': 'User Management', 'profile': 'User Management',
            'payments': 'Payment Processing', 'payment': 'Payment Processing', 'checkout': 'Payment Processing',
            'cart': 'Shopping Cart', 'shopping': 'Shopping Cart',
            'search': 'Search', 'notification': 'Notifications', 'notifications': 'Notifications',
            'admin': 'Administration', 'report': 'Reporting', 'reports': 'Reporting', 'analytics': 'Analytics',
        }
    )

    # Jira base URL for clickable links
    jira_base_url: Optional[str] = None # e.g. "https://jira.example.com/browse/"

    def get_config_for_path(self, file_path: str) -> Dict[str, str]:
        """Get the most specific variable mapping for a given file path."""
        if not self.scoped_url_mappings:
            return self.base_url_mapping
            
        norm_path = re.sub(r'\\', '/', file_path)
        
        # Sort keys by length descending to match longest (most specific) path first
        sorted_dirs = sorted(self.scoped_url_mappings.keys(), key=len, reverse=True)
        
        for d in sorted_dirs:
            if norm_path.startswith(d):
                # Found a matching directory, merge with base mapping
                merged = self.base_url_mapping.copy()
                merged.update(self.scoped_url_mappings[d])
                return merged
                
        return self.base_url_mapping


@dataclass
class Project:
    """Registered Karate project."""

    name: str
    root_path: str
    feature_file_patterns: List[str] = field(default_factory=lambda: ["**/*.feature"])
    parser_config: ParserConfig = field(default_factory=ParserConfig)


@dataclass
class FeatureAST:
    """Abstract Syntax Tree representation of a parsed feature file."""

    file_path: str
    feature_name: Optional[str]
    scenarios: List[Scenario]
    background_steps: List[Step] = field(default_factory=list)


@dataclass
class PathContext:
    """Context for resolving relative paths in feature files."""

    current_file_path: str
    project_root: str
    parser_config: ParserConfig


class InvertedIndices:
    """Fast lookup indices for common queries."""

    def __init__(self) -> None:
        self.jira_tag_index: Dict[str, List[str]] = {}  # tag → [node_ids]
        self.api_endpoint_index: Dict[str, List[str]] = {}  # endpoint → [node_ids]
        self.page_object_index: Dict[str, List[str]] = {}  # page → [node_ids]
        self.database_op_index: Dict[str, List[str]] = {}  # operation → [node_ids]
        self.scenario_tag_index: Dict[str, List[str]] = {}  # @tag → [scenario_node_ids]
        self.action_tag_index: Dict[str, List[str]] = {}  # @tag → [action_node_ids]
        self.domain_index: Dict[str, List[str]] = {}  # domain → [api_node_ids]
        self.http_method_index: Dict[str, List[str]] = {}  # method → [api_node_ids]
        self.data_file_index: Dict[str, List[str]] = {}  # file_path → [data_node_ids]

    def _add_to_index(self, index: Dict[str, List[str]], key: str, node_id: str) -> None:
        """Helper to add a key to a specific index dictionary."""
        if not key:
            return
        if key not in index:
            index[key] = []
        if node_id not in index[key]:
            index[key].append(node_id)

    def add_jira_tag(self, tag: str, node_id: str) -> None:
        """Add a Jira tag to node mapping."""
        self._add_to_index(self.jira_tag_index, tag, node_id)

    def add_api_endpoint(self, endpoint: str, node_id: str) -> None:
        """Add an API endpoint to node mapping."""
        self._add_to_index(self.api_endpoint_index, endpoint, node_id)

    def add_page_object(self, page: str, node_id: str) -> None:
        """Add a page object to node mapping."""
        self._add_to_index(self.page_object_index, page, node_id)

    def add_database_op(self, operation: str, node_id: str) -> None:
        """Add a database operation to node mapping."""
        self._add_to_index(self.database_op_index, operation, node_id)
    
    def add_scenario_tag(self, tag: str, node_id: str) -> None:
        """Add a scenario tag to node mapping."""
        self._add_to_index(self.scenario_tag_index, tag, node_id)
    
    def add_action_tag(self, tag: str, node_id: str) -> None:
        """Add an action tag to node mapping."""
        self._add_to_index(self.action_tag_index, tag, node_id)
    
    def add_domain(self, domain: str, node_id: str) -> None:
        """Add a domain to API node mapping."""
        self._add_to_index(self.domain_index, domain, node_id)
        
    def add_http_method(self, method: str, node_id: str) -> None:
        """Add an HTTP method to API node mapping."""
        self._add_to_index(self.http_method_index, method, node_id)

    def add_data_file(self, file_path: str, node_id: str) -> None:
        """Add a data file path to node mapping."""
        self._add_to_index(self.data_file_index, file_path, node_id)

    def get_by_jira_tag(self, tag: str) -> List[str]:
        """Get all node IDs associated with a Jira tag."""
        return self.jira_tag_index.get(tag, [])

    def get_by_data_file(self, file_path: str) -> List[str]:
        """Get all node IDs associated with a data file."""
        return self.data_file_index.get(file_path, [])

    def get_by_api_endpoint(self, endpoint: str) -> List[str]:
        """Get all node IDs associated with an API endpoint."""
        return self.api_endpoint_index.get(endpoint, [])

    def get_by_page_object(self, page: str) -> List[str]:
        """Get all node IDs associated with a page object."""
        return self.page_object_index.get(page, [])

    def get_by_database_op(self, operation: str) -> List[str]:
        """Get all node IDs associated with a database operation."""
        return self.database_op_index.get(operation, [])
    
    def get_by_scenario_tag(self, tag: str) -> List[str]:
        """Get all scenario node IDs associated with a tag."""
        return self.scenario_tag_index.get(tag, [])
    
    def get_by_action_tag(self, tag: str) -> List[str]:
        """Get all action node IDs associated with a tag."""
        return self.action_tag_index.get(tag, [])
    
    def get_by_domain(self, domain: str) -> List[str]:
        """Get all API node IDs associated with a domain."""
        return self.domain_index.get(domain, [])
    
    def get_by_http_method(self, method: str) -> List[str]:
        """Get all API node IDs associated with an HTTP method."""
        return self.http_method_index.get(method, [])

    def build_from_graph(self, graph: "DependencyGraph") -> None:
        """Build all inverted indices from a dependency graph."""
        # Clear existing indices
        self.jira_tag_index.clear()
        self.api_endpoint_index.clear()
        self.page_object_index.clear()
        self.database_op_index.clear()
        self.scenario_tag_index.clear()
        self.action_tag_index.clear()
        self.domain_index.clear()
        self.http_method_index.clear()
        self.data_file_index.clear()
        
        # Build indices by scanning all nodes
        for node_id, node in graph.nodes.items():
            # Index Jira tags (from all nodes that have them)
            for tag in node.metadata.jira_tags:
                self.add_jira_tag(tag, node_id)
            
            # Index by node type
            if node.type == NodeType.API:
                self.add_api_endpoint(node.name, node_id)
                
                # Multi-key environment indexing
                for variant in node.metadata.environment_variants:
                    self.add_api_endpoint(variant, node_id)

                for key in ("full_url", "path", "path_template", "physical_url"):
                    endpoint = node.metadata.additional_data.get(key)
                    if endpoint:
                        self.add_api_endpoint(endpoint, node_id)
                
                domain = node.metadata.additional_data.get('domain')
                if domain:
                    self.add_domain(domain, node_id)
                
                http_method = node.metadata.additional_data.get('http_method')
                if http_method:
                    self.add_http_method(http_method, node_id)
                    
            elif node.type == NodeType.PAGE:
                self.add_page_object(node.name, node_id)
                
            elif node.type == NodeType.DATABASE:
                self.add_database_op(node.name, node_id)
                
            elif node.type == NodeType.SCENARIO:
                scenario_tag = node.metadata.additional_data.get('scenario_tag')
                if scenario_tag:
                    self.add_scenario_tag(scenario_tag, node_id)
                    
            elif node.type == NodeType.ACTION:
                action_tag = node.metadata.additional_data.get('action_tag')
                if action_tag:
                    self.add_action_tag(action_tag, node_id)
            
            elif node.type == NodeType.DATA:
                self.add_data_file(node.name, node_id)
                # Index environment-specific physical paths
                for variant in node.metadata.environment_variants:
                    self.add_data_file(variant, node_id)
                
                physical_path = node.metadata.additional_data.get('physical_path')
                if physical_path:
                    self.add_data_file(physical_path, node_id)


@dataclass
class ParseError(Exception):
    """Exception raised when parsing fails."""

    file_path: str
    line_number: Optional[int]
    message: str
    error_code: str = "1001"

    def __str__(self) -> str:
        location = f"{self.file_path}"
        if self.line_number is not None:
            location += f":{self.line_number}"
        return f"[{self.error_code}] {location}: {self.message}"
@dataclass
class FixEntry:
    """Represents a historical fix for a component and error pattern."""
    node_id: str
    name: str
    error_pattern: str
    solution: str
    description: str
    timestamp: str
    success_count: int = 1
    file_path: Optional[str] = None
