"""
Data models for the Karate Feature Graph Analyzer.

This module contains all dataclasses and enums representing the core domain models
as specified in the design document.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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


@dataclass
class Step:
    """Represents a single step in a scenario."""

    keyword: str  # Given, When, Then, And, But
    text: str
    line_number: int


@dataclass
class Examples:
    """Represents an Examples block in a Scenario Outline."""

    headers: List[str]
    rows: List[List[str]]
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
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Node:
    """Graph node representing a test component."""

    id: str
    type: NodeType
    name: str
    metadata: NodeMetadata


@dataclass
class Edge:
    """Directed edge representing dependency relationship."""

    id: str
    from_node: str
    to_node: str
    type: DependencyType


@dataclass
class DependencyGraph:
    """Complete dependency graph for a project."""

    project_name: str
    nodes: Dict[str, Node]
    edges: Dict[str, Edge]
    cycles: List[List[str]] = field(default_factory=list)

    def merge(self, other: "DependencyGraph", new_project_name: Optional[str] = None) -> "DependencyGraph":
        """Merge another graph into this one."""
        if new_project_name:
            self.project_name = new_project_name
            
        self.nodes.update(other.nodes)
        self.edges.update(other.edges)
        
        for cycle in other.cycles:
            if cycle not in self.cycles:
                self.cycles.append(cycle)
                
        return self


@dataclass
class AffectedTestCase:
    """Test case affected by a change."""

    node_id: str
    name: str
    jira_tags: List[str]
    dependency_path: List[str]  # Path from test case to changed component
    depth: int


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
            r"@[A-Z]+-\d+",      # @PROJ-123 (uppercase with hyphen)
            r"@[a-z]+-\d+",      # @proj-123 (lowercase with hyphen)
            r"@[A-Za-z]+-\d+",   # @Proj-123 (mixed case with hyphen)
            r"@[A-Z]+_\d+",      # @PROJ_123 (uppercase with underscore)
            r"@[a-z]+_\d+",      # @proj_123 (lowercase with underscore)
            r"@[A-Za-z]+_\d+",   # @Proj_123 (mixed case with underscore)
        ]
    )
    workflow_directories: List[str] = field(default_factory=lambda: ["workflow", "workflows"])
    common_directories: List[str] = field(default_factory=lambda: ["common", "services"])
    page_object_directories: List[str] = field(default_factory=lambda: ["pages", "webPages"])
    locator_directories: List[str] = field(default_factory=lambda: ["locators", "resources/locators"])
    variable_patterns: Dict[str, str] = field(default_factory=dict)
    api_extraction_rules: List[str] = field(
        default_factory=lambda: [
            r"url\s+['\"]([^'\"]+)['\"]",  # url 'http://...'
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

    def add_jira_tag(self, tag: str, node_id: str) -> None:
        """Add a Jira tag to node mapping."""
        if tag not in self.jira_tag_index:
            self.jira_tag_index[tag] = []
        if node_id not in self.jira_tag_index[tag]:
            self.jira_tag_index[tag].append(node_id)

    def add_api_endpoint(self, endpoint: str, node_id: str) -> None:
        """Add an API endpoint to node mapping."""
        if endpoint not in self.api_endpoint_index:
            self.api_endpoint_index[endpoint] = []
        if node_id not in self.api_endpoint_index[endpoint]:
            self.api_endpoint_index[endpoint].append(node_id)

    def add_page_object(self, page: str, node_id: str) -> None:
        """Add a page object to node mapping."""
        if page not in self.page_object_index:
            self.page_object_index[page] = []
        if node_id not in self.page_object_index[page]:
            self.page_object_index[page].append(node_id)

    def add_database_op(self, operation: str, node_id: str) -> None:
        """Add a database operation to node mapping."""
        if operation not in self.database_op_index:
            self.database_op_index[operation] = []
        if node_id not in self.database_op_index[operation]:
            self.database_op_index[operation].append(node_id)
    
    def add_scenario_tag(self, tag: str, node_id: str) -> None:
        """Add a scenario tag to node mapping."""
        if tag not in self.scenario_tag_index:
            self.scenario_tag_index[tag] = []
        if node_id not in self.scenario_tag_index[tag]:
            self.scenario_tag_index[tag].append(node_id)
    
    def add_action_tag(self, tag: str, node_id: str) -> None:
        """Add an action tag to node mapping."""
        if tag not in self.action_tag_index:
            self.action_tag_index[tag] = []
        if node_id not in self.action_tag_index[tag]:
            self.action_tag_index[tag].append(node_id)
    
    def add_domain(self, domain: str, node_id: str) -> None:
        """Add a domain to API node mapping."""
        if domain not in self.domain_index:
            self.domain_index[domain] = []
        if node_id not in self.domain_index[domain]:
            self.domain_index[domain].append(node_id)
    
    def add_http_method(self, method: str, node_id: str) -> None:
        """Add an HTTP method to API node mapping."""
        if method not in self.http_method_index:
            self.http_method_index[method] = []
        if node_id not in self.http_method_index[method]:
            self.http_method_index[method].append(node_id)

    def get_by_jira_tag(self, tag: str) -> List[str]:
        """Get all node IDs associated with a Jira tag."""
        return self.jira_tag_index.get(tag, [])

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
        """Build all inverted indices from a dependency graph.
        
        This method populates all indices by scanning the graph:
        - jira_tag_index: Maps Jira tags to test case node IDs
        - api_endpoint_index: Maps API endpoints to node IDs
        - page_object_index: Maps page objects to node IDs
        - database_op_index: Maps database operations to node IDs
        - scenario_tag_index: Maps scenario tags to scenario node IDs
        - action_tag_index: Maps action tags to action node IDs
        - domain_index: Maps domains to API node IDs
        - http_method_index: Maps HTTP methods to API node IDs
        
        Args:
            graph: DependencyGraph to build indices from
        """
        # Clear existing indices
        self.jira_tag_index.clear()
        self.api_endpoint_index.clear()
        self.page_object_index.clear()
        self.database_op_index.clear()
        self.scenario_tag_index.clear()
        self.action_tag_index.clear()
        self.domain_index.clear()
        self.http_method_index.clear()
        
        # Build indices by scanning all nodes
        for node_id, node in graph.nodes.items():
            # Index Jira tags (from all nodes that have them)
            for tag in node.metadata.jira_tags:
                self.add_jira_tag(tag, node_id)
            
            # Index by node type
            if node.type == NodeType.API:
                # API nodes: index by endpoint (node name)
                self.add_api_endpoint(node.name, node_id)
                
                # Index by domain
                domain = node.metadata.additional_data.get('domain')
                if domain:
                    self.add_domain(domain, node_id)
                
                # Index by HTTP method
                http_method = node.metadata.additional_data.get('http_method')
                if http_method:
                    self.add_http_method(http_method, node_id)
                    
            elif node.type == NodeType.PAGE:
                # Page nodes: index by page path (node name)
                self.add_page_object(node.name, node_id)
                
            elif node.type == NodeType.DATABASE:
                # Database nodes: index by operation (node name)
                self.add_database_op(node.name, node_id)
                
            elif node.type == NodeType.SCENARIO:
                # Scenario nodes: index by scenario tag
                scenario_tag = node.metadata.additional_data.get('scenario_tag')
                if scenario_tag:
                    self.add_scenario_tag(scenario_tag, node_id)
                    
            elif node.type == NodeType.ACTION:
                # Action nodes: index by action tag
                action_tag = node.metadata.additional_data.get('action_tag')
                if action_tag:
                    self.add_action_tag(action_tag, node_id)


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
