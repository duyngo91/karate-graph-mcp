"""
Graph builder implementation.

Constructs dependency graphs from parsed feature files.
Supports Dependency Injection for parser (testability).
"""

from typing import TYPE_CHECKING, Dict, List, Optional

import networkx as nx

from karate_graph_analyzer.models import (
    Dependency,
    DependencyGraph,
    DependencyType,
    Edge,
    Node,
    NodeMetadata,
    NodeType,
    Project,
    Scenario,
)

if TYPE_CHECKING:
    from karate_graph_analyzer.cache.cache_manager import CacheManager
    from karate_graph_analyzer.parser.feature_parser import FeatureFileParser


class GraphBuilder:
    """Constructs dependency graph from parsed feature files.

    Supports Dependency Injection for the parser to enable
    testing with mock parsers and custom parsing strategies.
    """

    def __init__(self, parser: Optional["FeatureFileParser"] = None) -> None:
        """Initialize graph builder with empty graph.

        Args:
            parser: Optional parser instance (DI). If None, a default
                    FeatureFileParser is created when needed.
        """
        self.graph: nx.DiGraph = nx.DiGraph()
        self._node_counter: Dict[str, int] = {}  # Track node IDs by type
        self._injected_parser = parser  # DI: injectable parser

    def _generate_node_id(self, node_type: NodeType) -> str:
        """Generate unique node ID for a given node type.

        Args:
            node_type: Type of node

        Returns:
            Unique node ID string
        """
        # Use short prefixes for node types
        prefix_map = {
            NodeType.TEST_CASE: "tc",
            NodeType.WORKFLOW: "wf",
            NodeType.SCENARIO: "scn",
            NodeType.API: "api",
            NodeType.API_GROUP: "apig",
            NodeType.PAGE: "page",
            NodeType.ACTION: "act",
            NodeType.DATABASE: "db",
        }
        prefix = prefix_map.get(node_type, "node")
        
        # Increment counter for this type
        if prefix not in self._node_counter:
            self._node_counter[prefix] = 0
        self._node_counter[prefix] += 1
        
        return f"{prefix}_{self._node_counter[prefix]:04d}"

    def add_test_case(self, scenario: Scenario, metadata: NodeMetadata) -> str:
        """Add test case node to graph.

        Args:
            scenario: Scenario to add as a node
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        # Generate unique node ID
        node_id = self._generate_node_id(NodeType.TEST_CASE)
        
        # Create display name with Jira tags
        display_name = scenario.name
        if scenario.jira_tags:
            # Use first Jira tag in display name
            jira_tag = scenario.jira_tags[0]
            display_name = f"{jira_tag} - {scenario.name}"
        
        # Create node with metadata
        node_data = {
            "id": node_id,
            "type": NodeType.TEST_CASE,
            "name": display_name,  # Use display name with Jira tag
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
            # Store scenario-specific data
            "scenario_type": scenario.type,
            "tags": scenario.tags,
            "original_name": scenario.name,  # Keep original name
        }
        
        # Add node to graph
        self.graph.add_node(node_id, **node_data)
        
        return node_id

    def add_workflow_node(self, name: str, metadata: NodeMetadata) -> str:
        """Add workflow node to graph.

        Args:
            name: Workflow name (typically file path)
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        node_id = self._generate_node_id(NodeType.WORKFLOW)
        
        node_data = {
            "id": node_id,
            "type": NodeType.WORKFLOW,
            "name": name,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_api_node(self, endpoint: str, metadata: NodeMetadata) -> str:
        """Add API call node to graph.

        Args:
            endpoint: API endpoint URL
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        node_id = self._generate_node_id(NodeType.API)
        
        node_data = {
            "id": node_id,
            "type": NodeType.API,
            "name": endpoint,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        
        self.graph.add_node(node_id, **node_data)
        return node_id
    
    def add_api_group_node(self, group_name: str, metadata: NodeMetadata) -> str:
        """Add API group node to graph (for hierarchical structure).

        Args:
            group_name: API group name (domain or path segment)
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        node_id = self._generate_node_id(NodeType.API_GROUP)
        
        node_data = {
            "id": node_id,
            "type": NodeType.API_GROUP,
            "name": group_name,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_page_node(self, page_path: str, metadata: NodeMetadata) -> str:
        """Add page object node to graph.

        Args:
            page_path: Page object file path
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        node_id = self._generate_node_id(NodeType.PAGE)
        
        node_data = {
            "id": node_id,
            "type": NodeType.PAGE,
            "name": page_path,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_database_node(self, operation: str, metadata: NodeMetadata) -> str:
        """Add database operation node to graph.

        Args:
            operation: Database operation identifier
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        node_id = self._generate_node_id(NodeType.DATABASE)
        
        node_data = {
            "id": node_id,
            "type": NodeType.DATABASE,
            "name": operation,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        
        self.graph.add_node(node_id, **node_data)
        self.graph.add_node(node_id, **node_data)
        return node_id
    
    def add_locator_node(self, locator_path: str, metadata: NodeMetadata) -> str:
        """Add locator object node to graph.

        Args:
            locator_path: Locator file path
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        node_id = self._generate_node_id(NodeType.LOCATOR)
        
        node_data = {
            "id": node_id,
            "type": NodeType.LOCATOR,
            "name": locator_path,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        
        self.graph.add_node(node_id, **node_data)
        return node_id
    
    def add_scenario_node(self, scenario_tag: str, workflow_path: str, metadata: NodeMetadata) -> str:
        """Add scenario node to graph (workflow scenario like @AddPayment).

        Args:
            scenario_tag: Scenario tag (e.g., '@AddPayment')
            workflow_path: Parent workflow file path
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        node_id = self._generate_node_id(NodeType.SCENARIO)
        
        # Ensure scenario_tag starts with @
        if not scenario_tag.startswith('@'):
            scenario_tag = f'@{scenario_tag}'
        
        node_data = {
            "id": node_id,
            "type": NodeType.SCENARIO,
            "name": scenario_tag,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": {
                    **metadata.additional_data,
                    "scenario_tag": scenario_tag,
                    "workflow_path": workflow_path,
                },
            },
        }
        
        self.graph.add_node(node_id, **node_data)
        return node_id
    
    def add_action_node(self, action_tag: str, page_path: str, metadata: NodeMetadata) -> str:
        """Add action node to graph (page action like @login).

        Args:
            action_tag: Action tag (e.g., '@login')
            page_path: Parent page file path
            metadata: Node metadata

        Returns:
            Node ID of the created node
        """
        node_id = self._generate_node_id(NodeType.ACTION)
        
        # Ensure action_tag starts with @
        if not action_tag.startswith('@'):
            action_tag = f'@{action_tag}'
        
        node_data = {
            "id": node_id,
            "type": NodeType.ACTION,
            "name": action_tag,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": {
                    **metadata.additional_data,
                    "action_tag": action_tag,
                    "page_path": page_path,
                },
            },
        }
        
        self.graph.add_node(node_id, **node_data)
        return node_id



    def _classify_scenario_by_path(
        self, file_path: str, config: "ParserConfig" = None
    ) -> NodeType:
        """Classify a scenario's node type based on its file path.

        Karate project convention:
        - `*/features/*` → TEST_CASE (actual test scenarios)
        - `*/common/*`, `*/services/*`, `*/workflows/*` → WORKFLOW (reusable functions)
        - `*/pages/*`, `*/webPages/*` → PAGE (page objects)
        - `*/db/*` → DATABASE
        - Everything else → TEST_CASE (default)

        Args:
            file_path: Path to the feature file
            config: Optional ParserConfig with custom directory patterns

        Returns:
            NodeType for the scenario
        """
        normalized = file_path.replace('\\', '/').lower()

        # Check for page object directories
        page_dirs = ['pages', 'webpages']
        if config and config.page_object_directories:
            page_dirs = [d.lower() for d in config.page_object_directories]
        for d in page_dirs:
            if f'/{d}/' in normalized:
                return NodeType.PAGE

        # Check for workflow directories
        workflow_dirs = ['workflows', 'workflow']
        if config and config.workflow_directories:
            workflow_dirs = [d.lower() for d in config.workflow_directories]
        for d in workflow_dirs:
            if f'/{d}/' in normalized:
                return NodeType.WORKFLOW
                
        # Check for common/API directories
        common_dirs = ['common', 'services']
        if config and hasattr(config, 'common_directories'):
            common_dirs = [d.lower() for d in config.common_directories]
        for d in common_dirs:
            if f'/{d}/' in normalized:
                return NodeType.COMMON

        # Check for database directories
        if '/db/' in normalized or '/database/' in normalized:
            return NodeType.DATABASE

        # Default: TEST_CASE (files in features/ or any other location)
        return NodeType.TEST_CASE

    def _build_scenario_display_name(self, scenario: Scenario, node_type: NodeType) -> str:
        """Build display name for a scenario based on its node type.

        For TEST_CASE: uses Jira tag + name (e.g., '@JiraId-1 - Test send payment success')
        For WORKFLOW: uses @tag as name (e.g., '@AddPayment')
        For PAGE: uses @tag as name (e.g., '@login')

        Args:
            scenario: Scenario to build name for
            node_type: Classified node type

        Returns:
            Display name string
        """
        if node_type == NodeType.TEST_CASE:
            # Test case: use Jira tag + scenario name
            if scenario.jira_tags:
                return f"{scenario.jira_tags[0]} - {scenario.name}"
            return scenario.name
        else:
            # Workflow/Page: use first @tag as display name
            if scenario.tags:
                return scenario.tags[0]  # e.g., '@AddPayment'
            return scenario.name or f"Unnamed at line {scenario.line_number}"
    
    def _detect_feature_from_path(self, file_path: str) -> str:
        """Detect feature name from file path.
        
        Excludes pages, services, and common directories from feature grouping.
        
        Args:
            file_path: Path to feature file
        
        Returns:
            Feature name (e.g., "Authentication", "Order Management") or None if should be excluded
        """
        import os
        
        # Normalize path separators
        normalized_path = file_path.replace('\\', '/').lower()
        
        # EXCLUDE paths that should NOT have feature groups
        # These already have their own node types (PAGE, WORKFLOW, etc.)
        exclude_patterns = [
            '/pages/',      # Page objects
            '/page/',
            '/services/',   # Workflow services
            '/service/',
            '/common/',     # Common utilities
            '/workflows/',  # Workflows
            '/workflow/',
        ]
        
        for pattern in exclude_patterns:
            if pattern in normalized_path:
                return None  # Don't create feature group for these
        
        # Feature detection rules based on directory names
        feature_map = {
            'authentication': 'Authentication',
            'auth': 'Authentication',
            'login': 'Authentication',
            'orders': 'Order Management',
            'order': 'Order Management',
            'products': 'Product Catalog',
            'product': 'Product Catalog',
            'catalog': 'Product Catalog',
            'users': 'User Management',
            'user': 'User Management',
            'profile': 'User Management',
            'payments': 'Payment Processing',
            'payment': 'Payment Processing',
            'checkout': 'Payment Processing',
            'cart': 'Shopping Cart',
            'shopping': 'Shopping Cart',
            'search': 'Search',
            'notification': 'Notifications',
            'notifications': 'Notifications',
            'admin': 'Administration',
            'report': 'Reporting',
            'reports': 'Reporting',
            'analytics': 'Analytics',
        }
        
        # Check each segment in the path
        path_segments = normalized_path.split('/')
        for segment in path_segments:
            if segment in feature_map:
                return feature_map[segment]
        
        # Fallback: use the parent directory name
        if len(path_segments) >= 2:
            parent_dir = path_segments[-2]
            # Capitalize first letter
            return parent_dir.replace('-', ' ').replace('_', ' ').title()
        
        return "Other"

    def add_dependency(
        self, from_node: str, to_node: str, dep_type: DependencyType
    ) -> str:
        """Add directed edge representing dependency.

        Args:
            from_node: Source node ID
            to_node: Target node ID
            dep_type: Type of dependency

        Returns:
            Edge ID of the created edge
        """
        # Generate unique edge ID
        edge_id = f"edge_{from_node}_{to_node}_{dep_type.value}"
        
        # Create edge with metadata
        edge_data = {
            "id": edge_id,
            "from_node": from_node,
            "to_node": to_node,
            "type": dep_type,
        }
        
        # Add edge to graph
        self.graph.add_edge(from_node, to_node, **edge_data)
        
        return edge_id

    def detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies using DFS.

        Uses NetworkX's simple_cycles algorithm to find all elementary cycles
        in the directed graph. An elementary cycle is a closed path where no
        node appears twice except the start/end node.

        Returns:
            List of cycle paths (each cycle is a list of node IDs)
        """
        try:
            # Use NetworkX's simple_cycles to find all elementary cycles
            # This uses Johnson's algorithm which is efficient for finding all cycles
            cycles = list(nx.simple_cycles(self.graph))
            
            # Mark cycles in graph metadata by storing them as a graph attribute
            self.graph.graph['cycles'] = cycles
            
            return cycles
        except Exception as e:
            # If cycle detection fails, return empty list and log the error
            # This ensures graceful degradation
            import logging
            logging.warning(f"Cycle detection failed: {e}")
            return []

    def build_from_project(self, project: Project) -> DependencyGraph:
        """Build complete graph for a project.

        Args:
            project: Project to build graph for

        Returns:
            Complete dependency graph for the project
        """
        import glob
        import logging
        import os
        from pathlib import Path
        
        from karate_graph_analyzer.models import ParseError

        logger = logging.getLogger(__name__)

        # Use injected parser or create default
        if self._injected_parser is not None:
            parser = self._injected_parser
        else:
            from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
            parser = FeatureFileParser(config=project.parser_config)
        
        # Track dependency nodes to avoid duplicates
        # Key: (node_type, name) -> node_id
        dependency_node_map: Dict[tuple, str] = {}
        
        # Find all feature files using project patterns
        feature_files = []
        for pattern in project.feature_file_patterns:
            # Construct full pattern path
            full_pattern = os.path.join(project.root_path, pattern)
            # Use glob to find matching files
            matched_files = glob.glob(full_pattern, recursive=True)
            feature_files.extend(matched_files)
        
        # Remove duplicates and sort for consistent ordering
        feature_files = sorted(set(feature_files))
        
        logger.info(f"Found {len(feature_files)} feature files in project '{project.name}'")
        
        # Pass 1: Parse all files, cache ASTs, and collect API dependencies from COMMON scenarios
        file_asts = []
        # Key: (normalized_path, tag) -> List[Dependency]
        common_api_deps_map: Dict[tuple, List] = {}
        
        for file_path in feature_files:
            try:
                # Parse the feature file
                ast = parser.parse_file(file_path)
                file_asts.append(ast)
                
                # Normalize file path for lookup
                norm_path = os.path.normpath(file_path).replace("\\", "/")
                
                for scenario in ast.scenarios:
                    scenario_node_type = self._classify_scenario_by_path(
                        scenario.file_path, project.parser_config
                    )
                    
                    if scenario_node_type == NodeType.COMMON:
                        # Extract API dependencies
                        dependencies = parser.extract_dependencies_with_background(
                            scenario, ast.background_steps, validate_paths=False
                        )
                        api_deps = [d for d in dependencies if d.type == DependencyType.API]
                        
                        # Inject file_path into API dependencies
                        for d in api_deps:
                            if "file_path" not in d.parameters:
                                d.parameters["file_path"] = scenario.file_path
                                
                        # Store by tag if available
                        for tag in scenario.tags:
                            common_api_deps_map[(norm_path, tag)] = api_deps
                            logger.info(f"DEBUG: Stored API deps for {(norm_path, tag)}: {len(api_deps)}")
                        # Also store a default mapping without tag (if called without tag)
                        if not scenario.tags:
                            common_api_deps_map[(norm_path, "")] = api_deps
                            logger.info(f"DEBUG: Stored default API deps for {(norm_path, '')}: {len(api_deps)}")
            except ParseError as e:
                logger.error(f"Parse error in {file_path}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error parsing {file_path}: {e}", exc_info=True)

        # Pass 2: Build nodes and edges
        for ast in file_asts:
            try:
                # Process each scenario in the feature file
                for scenario in ast.scenarios:
                    # === CLASSIFY scenario type based on file path ===
                    scenario_node_type = self._classify_scenario_by_path(
                        scenario.file_path, project.parser_config
                    )
                    
                    if scenario_node_type == NodeType.COMMON:
                        continue  # Skip creating nodes for COMMON scenarios
                    
                    # Build display name based on node type
                    display_name = self._build_scenario_display_name(scenario, scenario_node_type)

                    # Create scenario metadata
                    scenario_metadata = NodeMetadata(
                        file_path=scenario.file_path,
                        line_number=scenario.line_number,
                        jira_tags=scenario.jira_tags,
                        project_name=project.name,
                        additional_data={
                            "scenario_type": scenario.type.value,
                            "tags": scenario.tags,
                        },
                    )

                    # Extract Karate relative path for mapping (e.g. web/pages/LoginPage.feature)
                    rel_path = scenario.file_path.replace("\\", "/")
                    if "src/test/java/" in rel_path:
                        rel_path = rel_path.split("src/test/java/")[-1]
                    # Also try without features/ if present
                    if "features/" in rel_path:
                        rel_path = rel_path.split("features/")[-1]

                    # Create node with correct type
                    if scenario_node_type == NodeType.TEST_CASE:
                        node_id = self.add_test_case(scenario, scenario_metadata)
                    elif scenario_node_type == NodeType.WORKFLOW:
                        # Use workflow node for reusable service scenarios
                        node_id = self._generate_node_id(NodeType.WORKFLOW)
                        node_data = {
                            "id": node_id,
                            "type": NodeType.WORKFLOW,
                            "name": display_name,
                            "metadata": {
                                "file_path": scenario_metadata.file_path,
                                "line_number": scenario_metadata.line_number,
                                "jira_tags": scenario_metadata.jira_tags,
                                "project_name": scenario_metadata.project_name,
                                "additional_data": scenario_metadata.additional_data,
                            },
                        }
                        self.graph.add_node(node_id, **node_data)
                    elif scenario_node_type == NodeType.PAGE:
                        # CREATE FILE NODE (Purple Triangle)
                        file_key = (NodeType.PAGE, rel_path)
                        if file_key in dependency_node_map:
                            file_node_id = dependency_node_map[file_key]
                        else:
                            file_node_id = self.add_page_node(rel_path, scenario_metadata)
                            dependency_node_map[file_key] = file_node_id
                            
                        # CREATE ACTION NODE (Pink Diamond)
                        action_tag = display_name
                        action_key = (NodeType.ACTION, f"{rel_path}#{action_tag}")
                        if action_key in dependency_node_map:
                            node_id = dependency_node_map[action_key]
                        else:
                            node_id = self.add_action_node(action_tag, rel_path, scenario_metadata)
                            dependency_node_map[action_key] = node_id
                            
                        # LINK FILE -> ACTION
                        if not self.graph.has_edge(file_node_id, node_id):
                            self.add_dependency(file_node_id, node_id, DependencyType.PAGE)
                    else:
                        # Fallback to test case
                        node_id = self.add_test_case(scenario, scenario_metadata)
                    
                    # Extract dependencies from scenario
                    dependencies = parser.extract_dependencies_with_background(
                        scenario, 
                        ast.background_steps,
                        validate_paths=False
                    )
                    
                    # Process each dependency
                    for dep in dependencies:
                        if dep.type == DependencyType.COMMON:
                            tag = dep.parameters.get("scenario_tag", "")
                            if tag and not tag.startswith("@"):
                                tag = "@" + tag
                                
                            # Find API dependencies using endswith
                            api_deps = None
                            # Normalize dep target to avoid slash issues
                            target_norm = dep.target.replace("\\", "/")
                            
                            for map_path, map_tag in common_api_deps_map.keys():
                                if map_path.endswith(target_norm) and map_tag == tag:
                                    api_deps = common_api_deps_map.get((map_path, map_tag))
                                    break
                                    
                            if api_deps is None and tag:
                                # Fallback to default if specific tag not found
                                for map_path, map_tag in common_api_deps_map.keys():
                                    if map_path.endswith(target_norm) and map_tag == "":
                                        api_deps = common_api_deps_map.get((map_path, map_tag))
                                        break
                                
                            if api_deps:
                                for api_dep in api_deps:
                                    dep_node_id = self._get_or_create_dependency_node(
                                        api_dep, project.name, dependency_node_map
                                    )
                                    self.add_dependency(dep_node_id, node_id, api_dep.type)
                            continue

                        # Create dependency node (or reuse existing)
                        dep_node_id = self._get_or_create_dependency_node(
                            dep, project.name, dependency_node_map
                        )
                        
                        # REVERSED: Create edge from dependency to scenario node
                        self.add_dependency(dep_node_id, node_id, dep.type)
            
            except ParseError as e:
                # Log parsing error but continue with other files (graceful degradation)
                logger.error(f"Failed to parse {file_path}: {e}")
                continue
            except Exception as e:
                # Log unexpected errors but continue
                logger.error(f"Unexpected error processing {file_path}: {e}")
                continue
        
        # Detect cycles in the graph
        cycles = self.detect_cycles()
        
        if cycles:
            logger.warning(f"Detected {len(cycles)} circular dependencies in project '{project.name}'")
        
        # Build DependencyGraph object
        nodes_dict = {}
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            nodes_dict[node_id] = Node(
                id=node_data["id"],
                type=node_data["type"],
                name=node_data["name"],
                metadata=NodeMetadata(
                    file_path=node_data["metadata"].get("file_path"),
                    line_number=node_data["metadata"].get("line_number"),
                    jira_tags=node_data["metadata"].get("jira_tags", []),
                    project_name=node_data["metadata"].get("project_name", project.name),
                    additional_data=node_data["metadata"].get("additional_data", {}),
                ),
            )
        
        edges_dict = {}
        for from_node, to_node in self.graph.edges():
            edge_data = self.graph.edges[from_node, to_node]
            edge_id = edge_data["id"]
            edges_dict[edge_id] = Edge(
                id=edge_id,
                from_node=edge_data["from_node"],
                to_node=edge_data["to_node"],
                type=edge_data["type"],
            )
        
        return DependencyGraph(
            project_name=project.name,
            nodes=nodes_dict,
            edges=edges_dict,
            cycles=cycles,
        )
    
    def _parse_api_hierarchy(self, endpoint: str) -> List[str]:
        """Parse API endpoint into hierarchical segments.
        
        Examples:
            "test.com/api/v1/services_a/ham1" -> ["test.com", "api", "v1", "services_a", "ham1"]
            "${baseUrl}/api/users" -> ["${baseUrl}", "api", "users"]
            "/api/auth/login" -> ["api", "auth", "login"]
        
        Args:
            endpoint: API endpoint URL or path
        
        Returns:
            List of path segments from root to leaf
        """
        import re
        from urllib.parse import urlparse
        
        # Remove protocol if present (http://, https://)
        endpoint_clean = re.sub(r'^https?://', '', endpoint)
        
        # Try to parse as URL to extract domain and path
        if '://' in endpoint or endpoint.startswith('http'):
            parsed = urlparse(endpoint)
            domain = parsed.netloc
            path = parsed.path
        else:
            # Check if it starts with domain-like pattern (contains dots before slash)
            if '/' in endpoint_clean:
                first_part = endpoint_clean.split('/')[0]
                if '.' in first_part or first_part.startswith('${'):
                    # Likely has domain
                    domain = first_part
                    path = '/' + '/'.join(endpoint_clean.split('/')[1:])
                else:
                    # No domain, just path
                    domain = None
                    path = endpoint_clean if endpoint_clean.startswith('/') else '/' + endpoint_clean
            else:
                # Single segment (might be domain or variable)
                domain = endpoint_clean if ('.' in endpoint_clean or endpoint_clean.startswith('${')) else None
                path = '' if domain else '/' + endpoint_clean
        
        # Build hierarchy
        segments = []
        
        # Add domain if present
        if domain:
            segments.append(domain)
        
        # Add path segments (skip empty segments)
        if path:
            path_parts = [p for p in path.split('/') if p]
            segments.extend(path_parts)
        
        return segments
    
    def _create_api_hierarchy(
        self,
        endpoint: str,
        metadata: NodeMetadata,
        node_map: Dict[tuple, str]
    ) -> str:
        """Create hierarchical API structure and return leaf node ID.
        
        New structure: Domain → Path segments → Method {param}
        Example: ecommerce-api.example.com → api → orders → GET {id}
        
        Args:
            endpoint: Full API endpoint URL
            metadata: Metadata for the leaf node (contains http_method, path_template, examples)
            node_map: Map for deduplication
        
        Returns:
            Node ID of the leaf endpoint node
        """
        # Extract HTTP method and path template from metadata
        http_method = metadata.additional_data.get("http_method", "GET")
        path_template = metadata.additional_data.get("path_template", "")
        examples = metadata.additional_data.get("examples", [])
        base_url = metadata.additional_data.get("base_url", "")
        
        # Use path_template if available (has {id} instead of actual IDs)
        # Otherwise use endpoint
        if path_template and base_url:
            # Reconstruct URL with template
            template_url = f"{base_url}{path_template}"
            segments = self._parse_api_hierarchy(template_url)
        else:
            # Fallback to original endpoint
            segments = self._parse_api_hierarchy(endpoint)
        
        if not segments:
            # Fallback: create single API node
            return self._create_single_api_node(endpoint, metadata, node_map)
        
        # Filter out segments that are dynamic params (contain {})
        # Keep only static path segments for API_GROUP nodes
        static_segments = []
        for seg in segments:
            if '{' not in seg:
                static_segments.append(seg)
        
        # Determine leaf node name: "Method {param}" or just "Method"
        if path_template and "{" in path_template:
            # Extract param name from template (e.g., "/api/products/{id}" → "{id}")
            import re
            params = re.findall(r'\{([^}]+)\}', path_template)
            if params:
                leaf_name = f"{http_method} {{{params[-1]}}}"  # Use last param
            else:
                leaf_name = http_method
        else:
            leaf_name = http_method
        
        # Create hierarchy: ALL static segments become API_GROUP nodes
        # Then create a separate leaf API node with method name
        parent_node_id = None
        
        # Step 1: Create API_GROUP nodes for all static segments
        for i, segment in enumerate(static_segments):
            # Build cumulative path for this level
            cumulative_path = '/'.join(static_segments[:i+1])
            node_key = (NodeType.API_GROUP, cumulative_path)
            
            if node_key in node_map:
                current_node_id = node_map[node_key]
            else:
                # Determine display name:
                # - First segment (i=0): show full base_url if available, otherwise segment
                # - Other segments: show just the segment
                if i == 0 and base_url:
                    # First level - use full base URL as display name
                    display_name = base_url
                else:
                    # Other levels - use segment name
                    display_name = segment
                
                # Create new API_GROUP node
                group_metadata = NodeMetadata(
                    file_path=None,
                    line_number=None,
                    jira_tags=[],
                    project_name=metadata.project_name,
                    additional_data={"level": i, "segment": segment, "base_url": base_url if i == 0 else None},
                )
                current_node_id = self.add_api_group_node(display_name, group_metadata)
                node_map[node_key] = current_node_id
            
            # Connect to parent if exists
            if parent_node_id:
                # Check if edge already exists
                if not self.graph.has_edge(parent_node_id, current_node_id):
                    self.add_dependency(parent_node_id, current_node_id, DependencyType.API)
            
            parent_node_id = current_node_id
        
        # Step 2: Create leaf API node with method name
        # Use full endpoint + method as unique key
        node_key = (NodeType.API, f"{endpoint}#{http_method}")
        
        if node_key in node_map:
            leaf_node_id = node_map[node_key]
        else:
            # Update metadata with full info
            leaf_metadata = NodeMetadata(
                file_path=metadata.file_path,
                line_number=metadata.line_number,
                jira_tags=[],
                project_name=metadata.project_name,
                additional_data={
                    "full_url": endpoint,
                    "http_method": http_method,
                    "path_template": path_template,
                    "examples": examples,
                    "level": len(static_segments),
                },
            )
            # Create API node with method name (e.g., "GET {id}")
            leaf_node_id = self.add_api_node(leaf_name, leaf_metadata)
            node_map[node_key] = leaf_node_id
        
        # Connect leaf to last API_GROUP node
        if parent_node_id:
            if not self.graph.has_edge(parent_node_id, leaf_node_id):
                self.add_dependency(parent_node_id, leaf_node_id, DependencyType.API)
        
        return leaf_node_id
    
    def _create_single_api_node(
        self,
        endpoint: str,
        metadata: NodeMetadata,
        node_map: Dict[tuple, str]
    ) -> str:
        """Create a single API node without hierarchy (fallback).
        
        Args:
            endpoint: API endpoint
            metadata: Node metadata
            node_map: Map for deduplication
        
        Returns:
            Node ID of the API node
        """
        node_key = (NodeType.API, endpoint)
        
        if node_key in node_map:
            return node_map[node_key]
        
        node_id = self.add_api_node(endpoint, metadata)
        node_map[node_key] = node_id
        return node_id
    
    def _get_or_create_dependency_node(
        self, 
        dep: Dependency, 
        project_name: str,
        node_map: Dict[tuple, str]
    ) -> str:
        """Get existing dependency node or create a new one.
        
        Creates scenario/action nodes when scenario_tag is present in parameters.
        
        Args:
            dep: Dependency to create node for
            project_name: Name of the project
            node_map: Map of (node_type, name) -> node_id for deduplication
        
        Returns:
            Node ID of the dependency node (or scenario/action node if applicable)
        """
        # Determine node type from dependency type
        node_type_map = {
            DependencyType.WORKFLOW: NodeType.WORKFLOW,
            DependencyType.API: NodeType.API,
            DependencyType.PAGE: NodeType.PAGE,
            DependencyType.DATABASE: NodeType.DATABASE,
            DependencyType.LOCATOR: NodeType.LOCATOR,
        }
        
        node_type = node_type_map[dep.type]
        
        # Create metadata
        if dep.type in [DependencyType.WORKFLOW, DependencyType.PAGE, DependencyType.LOCATOR]:
            file_path = dep.target
        elif dep.type == DependencyType.API:
            file_path = dep.parameters.get("file_path")
        else:
            file_path = None
            
        metadata = NodeMetadata(
            file_path=file_path,
            line_number=dep.line_number,
            jira_tags=[],
            project_name=project_name,
            additional_data=dep.parameters,
        )
        
        # Create node based on type
        if dep.type == DependencyType.WORKFLOW:
            # Check if node already exists
            node_key = (node_type, dep.target)
            if node_key in node_map:
                workflow_node_id = node_map[node_key]
            else:
                workflow_node_id = self.add_workflow_node(dep.target, metadata)
                node_map[node_key] = workflow_node_id
            
            # Check if scenario_tag exists in parameters
            scenario_tag = dep.parameters.get('scenario_tag')
            if scenario_tag:
                # Create scenario node
                scenario_key = (NodeType.SCENARIO, f"{dep.target}#{scenario_tag}")
                
                if scenario_key in node_map:
                    scenario_node_id = node_map[scenario_key]
                else:
                    scenario_node_id = self.add_scenario_node(
                        scenario_tag=scenario_tag,
                        workflow_path=dep.target,
                        metadata=metadata
                    )
                    node_map[scenario_key] = scenario_node_id
                    
                    # Create edge: Workflow → Scenario
                    if not self.graph.has_edge(workflow_node_id, scenario_node_id):
                        self.add_dependency(workflow_node_id, scenario_node_id, dep.type)
                
                # Return scenario node ID (will be connected to test case)
                return scenario_node_id
            else:
                # No scenario tag, return workflow node (legacy behavior)
                return workflow_node_id
            
        elif dep.type == DependencyType.API:
            # Create hierarchical API structure
            return self._create_api_hierarchy(dep.target, metadata, node_map)
            
        elif dep.type == DependencyType.PAGE:
            # Check if node already exists
            node_key = (node_type, dep.target)
            if node_key in node_map:
                page_node_id = node_map[node_key]
            else:
                page_node_id = self.add_page_node(dep.target, metadata)
                node_map[node_key] = page_node_id
            
            # Check if scenario_tag exists in parameters (parser uses same key for actions)
            action_tag = dep.parameters.get('scenario_tag')
            if action_tag:
                # Create action node
                action_key = (NodeType.ACTION, f"{dep.target}#{action_tag}")
                
                if action_key in node_map:
                    action_node_id = node_map[action_key]
                else:
                    action_node_id = self.add_action_node(
                        action_tag=action_tag,
                        page_path=dep.target,
                        metadata=metadata
                    )
                    node_map[action_key] = action_node_id
                    
                    # Create edge: Page → Action
                    if not self.graph.has_edge(page_node_id, action_node_id):
                        self.add_dependency(page_node_id, action_node_id, dep.type)
                
                # Return action node ID (will be connected to test case)
                return action_node_id
            else:
                # No action tag, return page node (legacy behavior)
                return page_node_id
            
        elif dep.type == DependencyType.LOCATOR:
            # Check if node already exists
            node_key = (node_type, dep.target)
            if node_key in node_map:
                locator_node_id = node_map[node_key]
            else:
                locator_node_id = self.add_locator_node(dep.target, metadata)
                node_map[node_key] = locator_node_id
            return locator_node_id
            
        elif dep.type == DependencyType.DATABASE:
            # Check if node already exists
            node_key = (node_type, dep.target)
            if node_key in node_map:
                return node_map[node_key]
            
            node_id = self.add_database_node(dep.target, metadata)
            node_map[node_key] = node_id
            return node_id
        else:
            raise ValueError(f"Unknown dependency type: {dep.type}")

    
    def update_from_project(
        self, 
        project: Project, 
        existing_graph: DependencyGraph,
        cache_manager: "CacheManager"
    ) -> DependencyGraph:
        """Incrementally update graph for changed files in a project.
        
        This method detects which files have changed since the last analysis
        and only re-parses those files, updating the affected nodes and edges.
        This is more efficient than full re-analysis for large projects.
        
        Args:
            project: Project to update graph for
            existing_graph: Previously built dependency graph
            cache_manager: Cache manager to detect file changes
        
        Returns:
            Updated dependency graph with changes incorporated
        """
        import glob
        import logging
        import os
        
        from karate_graph_analyzer.models import ParseError

        logger = logging.getLogger(__name__)

        # Use injected parser or create default
        if self._injected_parser is not None:
            parser = self._injected_parser
        else:
            from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
            parser = FeatureFileParser(config=project.parser_config)
        
        # Find all feature files using project patterns
        feature_files = []
        for pattern in project.feature_file_patterns:
            full_pattern = os.path.join(project.root_path, pattern)
            matched_files = glob.glob(full_pattern, recursive=True)
            feature_files.extend(matched_files)
        
        feature_files = sorted(set(feature_files))
        
        # Detect changed and new files
        changed_files = []
        for file_path in feature_files:
            # Check if file is in cache and hasn't changed
            cached_ast = cache_manager.get(file_path)
            if cached_ast is None:
                # File is new or has changed
                changed_files.append(file_path)
        
        # If no files changed, return existing graph
        if not changed_files:
            logger.info(f"No file changes detected for project '{project.name}'")
            return existing_graph
        
        logger.info(f"Detected {len(changed_files)} changed files in project '{project.name}'")
        
        # Restore existing graph to this builder's internal state
        self.graph = nx.DiGraph()
        
        # Track the highest node counter for each type to avoid ID collisions
        for node_id, node in existing_graph.nodes.items():
            # Extract counter from node ID (e.g., "tc_0005" -> 5)
            parts = node_id.split('_')
            if len(parts) == 2:
                prefix = parts[0]
                try:
                    counter = int(parts[1])
                    if prefix not in self._node_counter:
                        self._node_counter[prefix] = 0
                    self._node_counter[prefix] = max(self._node_counter[prefix], counter)
                except ValueError:
                    pass
            
            node_data = {
                "id": node.id,
                "type": node.type,
                "name": node.name,
                "metadata": {
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                    "jira_tags": node.metadata.jira_tags,
                    "project_name": node.metadata.project_name,
                    "additional_data": node.metadata.additional_data,
                },
            }
            self.graph.add_node(node_id, **node_data)
        
        for edge_id, edge in existing_graph.edges.items():
            edge_data = {
                "id": edge.id,
                "from_node": edge.from_node,
                "to_node": edge.to_node,
                "type": edge.type,
            }
            self.graph.add_edge(edge.from_node, edge.to_node, **edge_data)
        
        # Track dependency nodes to avoid duplicates
        dependency_node_map: Dict[tuple, str] = {}
        
        # Build map of existing dependency nodes
        for node_id, node in existing_graph.nodes.items():
            if node.type != NodeType.TEST_CASE:
                node_key = (node.type, node.name)
                dependency_node_map[node_key] = node_id
        
        # Remove nodes and edges for changed files
        nodes_to_remove = []
        for node_id, node_data in self.graph.nodes(data=True):
            file_path = node_data.get("metadata", {}).get("file_path")
            if file_path in changed_files:
                nodes_to_remove.append(node_id)
        
        # Remove nodes and their associated edges
        for node_id in nodes_to_remove:
            # Remove from dependency map if present
            node_data = self.graph.nodes[node_id]
            node_type = node_data["type"]
            node_name = node_data["name"]
            node_key = (node_type, node_name)
            if node_key in dependency_node_map:
                del dependency_node_map[node_key]
            
            # Remove node (edges are automatically removed by networkx)
            self.graph.remove_node(node_id)
        
        logger.info(f"Removed {len(nodes_to_remove)} nodes from changed files")
        
        # Remove orphaned dependency nodes (nodes with no incoming edges)
        # These are dependency nodes that are no longer referenced by any test case
        orphaned_nodes = []
        for node_id, node_data in self.graph.nodes(data=True):
            node_type = node_data["type"]
            # Only check dependency nodes (not test cases)
            if node_type != NodeType.TEST_CASE:
                # Check if node has any incoming edges
                if self.graph.in_degree(node_id) == 0:
                    orphaned_nodes.append(node_id)
        
        # Remove orphaned nodes
        for node_id in orphaned_nodes:
            # Remove from dependency map if present
            node_data = self.graph.nodes[node_id]
            node_type = node_data["type"]
            node_name = node_data["name"]
            node_key = (node_type, node_name)
            if node_key in dependency_node_map:
                del dependency_node_map[node_key]
            
            self.graph.remove_node(node_id)
        
        if orphaned_nodes:
            logger.info(f"Removed {len(orphaned_nodes)} orphaned dependency nodes")
        
        # Re-parse changed files and add new nodes/edges
        for file_path in changed_files:
            try:
                # Parse the feature file
                ast = parser.parse_file(file_path)
                
                # Cache the parsed AST
                cache_manager.put(file_path, ast)
                
                # Process each scenario in the feature file
                for scenario in ast.scenarios:
                    # Create test case node
                    test_case_metadata = NodeMetadata(
                        file_path=scenario.file_path,
                        line_number=scenario.line_number,
                        jira_tags=scenario.jira_tags,
                        project_name=project.name,
                        additional_data={
                            "scenario_type": scenario.type.value,
                            "tags": scenario.tags,
                        },
                    )
                    
                    test_case_id = self.add_test_case(scenario, test_case_metadata)
                    
                    # Extract dependencies from scenario
                    dependencies = parser.extract_dependencies_with_background(
                        scenario, 
                        ast.background_steps,
                        validate_paths=False
                    )
                    
                    # Process each dependency
                    for dep in dependencies:
                        # Create dependency node (or reuse existing)
                        dep_node_id = self._get_or_create_dependency_node(
                            dep, project.name, dependency_node_map
                        )
                        
                        # REVERSED: Create edge from dependency to test case
                        # This makes dependencies (API/Page/DB) point to test cases
                        self.add_dependency(dep_node_id, test_case_id, dep.type)
                    
                    # Detect feature from file path
                    feature_name = self._detect_feature_from_path(scenario.file_path)
                    
                    # Only create feature group if feature_name is not None
                    # (excludes pages, services, common directories)
                    if feature_name is not None:
                        # Get or create feature group node
                        if feature_name not in feature_group_map:
                            feature_metadata = NodeMetadata(
                                file_path=None,
                                line_number=None,
                                jira_tags=[],
                                project_name=project.name,
                                additional_data={"feature_category": feature_name},
                            )
                            feature_group_id = self.add_feature_group_node(feature_name, feature_metadata)
                            feature_group_map[feature_name] = feature_group_id
                        else:
                            feature_group_id = feature_group_map[feature_name]
                        
                        # REVERSED: Create edge from feature group to test case
                        # This makes feature groups point to test cases (feature groups contain test cases)
                        self.add_dependency(feature_group_id, test_case_id, DependencyType.WORKFLOW)
            
            except ParseError as e:
                logger.error(f"Failed to parse {file_path}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error processing {file_path}: {e}")
                continue
        
        # Detect cycles in the updated graph
        cycles = self.detect_cycles()
        
        if cycles:
            logger.warning(f"Detected {len(cycles)} circular dependencies in project '{project.name}'")
        
        # Build updated DependencyGraph object
        nodes_dict = {}
        for node_id in self.graph.nodes():
            node_data = self.graph.nodes[node_id]
            nodes_dict[node_id] = Node(
                id=node_data["id"],
                type=node_data["type"],
                name=node_data["name"],
                metadata=NodeMetadata(
                    file_path=node_data["metadata"].get("file_path"),
                    line_number=node_data["metadata"].get("line_number"),
                    jira_tags=node_data["metadata"].get("jira_tags", []),
                    project_name=node_data["metadata"].get("project_name", project.name),
                    additional_data=node_data["metadata"].get("additional_data", {}),
                ),
            )
        
        edges_dict = {}
        for from_node, to_node in self.graph.edges():
            edge_data = self.graph.edges[from_node, to_node]
            edge_id = edge_data["id"]
            edges_dict[edge_id] = Edge(
                id=edge_id,
                from_node=edge_data["from_node"],
                to_node=edge_data["to_node"],
                type=edge_data["type"],
            )
        
        return DependencyGraph(
            project_name=project.name,
            nodes=nodes_dict,
            edges=edges_dict,
            cycles=cycles,
        )
