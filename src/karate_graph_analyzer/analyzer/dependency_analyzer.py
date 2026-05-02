"""
Dependency analyzer implementation.

Analyzes dependency graphs for impact and reusability.
"""

from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from karate_graph_analyzer.models import (
    AffectedTestCase,
    DependencyGraph,
    ImpactResult,
    InvertedIndices,
    Node,
    NodeType,
    Project,
    ReusableComponent,
    ComponentInstance,
    ParserConfig,
)


class DependencyAnalyzer:
    """Analyzes dependency graph for impact and reusability."""

    def __init__(self, graph: DependencyGraph) -> None:
        """Initialize analyzer with dependency graph.

        Args:
            graph: Dependency graph to analyze
        """
        import networkx as nx
        
        self.graph = graph
        self.indices = InvertedIndices()
        
        # Build inverted indices from the graph for fast lookups
        self.indices.build_from_graph(graph)
        
        # Build NetworkX graph once during initialization for efficient queries
        self._nx_graph = nx.DiGraph()
        
        # Add all nodes
        for node_id in self.graph.nodes.keys():
            self._nx_graph.add_node(node_id)
        
        # Add all edges
        for edge in self.graph.edges.values():
            self._nx_graph.add_edge(
                edge.from_node, 
                edge.to_node, 
                id=edge.id, 
                type=edge.type,
                line_number=edge.line_number
            )

        # Initialize expert analyzer
        from karate_graph_analyzer.analyzer.analysis_expert import AnalysisExpert
        self.expert = AnalysisExpert(self.graph, self._nx_graph)

    def impact_analysis(self, component_id: str) -> ImpactResult:
        """Find all test cases affected by component change.

        Args:
            component_id: ID of the changed component

        Returns:
            ImpactResult with affected test cases, dependency paths, depths
        """
        import networkx as nx
        
        # Check if component exists in the graph
        if component_id not in self.graph.nodes:
            # Return empty result if component not found
            return ImpactResult(
                changed_component=component_id,
                affected_test_cases=[],
                total_count=0,
            )

        if self.graph.nodes[component_id].type == NodeType.API_GROUP:
            return self._impact_analysis_api_group(component_id)
        
        # Perform reverse graph traversal to find all nodes that can reach the component
        # ancestors() returns all nodes that have a path TO the given node
        try:
            ancestor_ids = nx.ancestors(self._nx_graph, component_id)
        except nx.NetworkXError:
            # Node not in graph (shouldn't happen due to earlier check, but be safe)
            return ImpactResult(
                changed_component=component_id,
                affected_test_cases=[],
                total_count=0,
            )
        
        # Filter to only include TEST_CASE nodes
        affected_test_cases = []
        for ancestor_id in ancestor_ids:
            if ancestor_id not in self.graph.nodes:
                continue
            
            node = self.graph.nodes[ancestor_id]
            if node.type != NodeType.TEST_CASE:
                continue
            
            # Calculate all paths from this test case to the changed component
            try:
                all_paths = list(nx.all_simple_paths(self._nx_graph, ancestor_id, component_id))
            except (nx.NetworkXError, nx.NodeNotFound):
                # If no path exists (shouldn't happen since ancestor_id came from ancestors())
                continue
            
            # Find the shortest path for this test case (minimum depth)
            if not all_paths:
                continue
            
            shortest_path = min(all_paths, key=len)
            depth = len(shortest_path) - 1  # Number of edges = number of nodes - 1
            
            # Find the specific line number that causes the dependency
            # This is the line in the test case that calls the next component in the path
            line_number = node.metadata.line_number # Default to node start
            if len(shortest_path) >= 2:
                edge_data = self._nx_graph.get_edge_data(shortest_path[0], shortest_path[1])
                if edge_data and "line_number" in edge_data and edge_data["line_number"] is not None:
                    line_number = edge_data["line_number"]
            
            # Create AffectedTestCase object
            affected_test_case = AffectedTestCase(
                node_id=node.id,
                name=node.name,
                jira_tags=node.metadata.jira_tags,
                dependency_path=shortest_path,
                depth=depth,
                line_number=line_number,
            )
            affected_test_cases.append(affected_test_case)
        
        # Return ImpactResult
        return ImpactResult(
            changed_component=component_id,
            affected_test_cases=affected_test_cases,
            total_count=len(affected_test_cases),
        )

    def _impact_analysis_api_group(self, component_id: str) -> ImpactResult:
        """Aggregate impact for all API leaves below an API_GROUP node."""
        import networkx as nx

        try:
            descendant_ids = nx.descendants(self._nx_graph, component_id)
        except nx.NetworkXError:
            descendant_ids = set()

        affected_by_test: Dict[str, AffectedTestCase] = {}
        for descendant_id in descendant_ids:
            node = self.graph.nodes.get(descendant_id)
            if not node or node.type != NodeType.API:
                continue

            leaf_result = self.impact_analysis(descendant_id)
            for affected in leaf_result.affected_test_cases:
                path = list(affected.dependency_path)
                if component_id not in path:
                    path.append(component_id)
                candidate = AffectedTestCase(
                    node_id=affected.node_id,
                    name=affected.name,
                    jira_tags=affected.jira_tags,
                    dependency_path=path,
                    depth=affected.depth,
                    line_number=affected.line_number,
                )
                existing = affected_by_test.get(candidate.node_id)
                if existing is None or candidate.depth < existing.depth:
                    affected_by_test[candidate.node_id] = candidate

        affected_test_cases = sorted(
            affected_by_test.values(),
            key=lambda t: (t.depth, t.name, t.node_id),
        )
        return ImpactResult(
            changed_component=component_id,
            affected_test_cases=affected_test_cases,
            total_count=len(affected_test_cases),
        )

    def find_dependencies(self, node_id: str, transitive: bool = True) -> List[Node]:
        """Find direct or transitive dependencies.

        Args:
            node_id: Node to find dependencies for
            transitive: If True, find all transitive dependencies

        Returns:
            List of dependent nodes
        """
        import networkx as nx
        
        # Check if node exists in the graph
        if node_id not in self.graph.nodes:
            # Return empty list if node not found (graceful handling)
            return []
        
        # Find dependencies based on transitive flag using cached NetworkX graph
        if transitive:
            # Find all transitive dependencies (all descendants)
            # descendants() returns all nodes reachable from the source node
            try:
                dependency_ids = nx.descendants(self._nx_graph, node_id)
            except nx.NetworkXError:
                # Node not in graph (shouldn't happen due to earlier check, but be safe)
                return []
        else:
            # Find direct dependencies (immediate successors)
            # successors() returns nodes that the given node points to
            dependency_ids = list(self._nx_graph.successors(node_id))
        
        # Convert node IDs to Node objects
        result_nodes = []
        for dep_id in dependency_ids:
            if dep_id in self.graph.nodes:
                result_nodes.append(self.graph.nodes[dep_id])
        
        return result_nodes

    def find_common_components(
        self, projects: List[Project]
    ) -> List[ReusableComponent]:
        """Identify reusable workflows, APIs, pages across projects.

        Args:
            projects: List of projects to analyze

        Returns:
            List of reusable components with usage statistics
        """
        from karate_graph_analyzer.graph.graph_builder import GraphBuilder
        
        # Build graphs for all projects
        project_graphs: Dict[str, DependencyGraph] = {}
        for project in projects:
            builder = GraphBuilder()
            graph = builder.build_from_project(project)
            project_graphs[project.name] = graph
        
        # Track components across projects
        # Key: (node_type, name) -> List[ComponentInstance]
        component_instances: Dict[tuple, List] = defaultdict(list)
        
        # Collect all WORKFLOW, API, PAGE and COMMON nodes from all projects
        for project_name, graph in project_graphs.items():
            for node_id, node in graph.nodes.items():
                # Only consider WORKFLOW, API, PAGE and COMMON nodes
                if node.type not in [NodeType.WORKFLOW, NodeType.API, NodeType.PAGE, NodeType.COMMON]:
                    continue
                
                # Create component key (type, name)
                component_key = (node.type, node.name)
                
                # Create ComponentInstance
                instance = ComponentInstance(
                    project_name=project_name,
                    file_path=node.metadata.file_path or "",
                    node_id=node_id,
                )
                
                component_instances[component_key].append(instance)
        
        # Filter to only components that appear in multiple projects
        common_components = []
        for (node_type, name), instances in component_instances.items():
            # Get unique project names for this component
            unique_projects = set(instance.project_name for instance in instances)
            
            # Only include if component appears in multiple projects
            if len(unique_projects) < 2:
                continue
            
            # Calculate usage frequency (total count of nodes across all projects)
            usage_count = len(instances)
            
            # Create ReusableComponent
            reusable_component = ReusableComponent(
                type=node_type,
                name=name,
                usage_count=usage_count,
                instances=instances,
            )
            
            common_components.append(reusable_component)
        
        # Sort by usage frequency (descending)
        common_components.sort(key=lambda c: c.usage_count, reverse=True)
        
        return common_components

    def query_by_tag(self, jira_tag: str) -> List[Node]:
        """Fast lookup using inverted index.

        Args:
            jira_tag: Jira tag to search for

        Returns:
            List of nodes with the specified tag
        """
        # Use inverted index for O(1) lookup
        node_ids = self.indices.get_by_jira_tag(jira_tag)
        
        # Convert node IDs to Node objects
        result_nodes = []
        for node_id in node_ids:
            if node_id in self.graph.nodes:
                result_nodes.append(self.graph.nodes[node_id])
        
        return result_nodes
