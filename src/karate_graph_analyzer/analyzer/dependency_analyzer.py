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
        
        # Initialize fix expert
        from karate_graph_analyzer.analyzer.fix_expert import FixExpert
        self.fix_expert = FixExpert()

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
        
        # Filter to include TEST_CASE and SCENARIO nodes
        affected_test_cases = []
        for ancestor_id in ancestor_ids:
            if ancestor_id not in self.graph.nodes:
                continue
            
            node = self.graph.nodes[ancestor_id]
            if node.type not in [NodeType.TEST_CASE, NodeType.SCENARIO]:
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
        """Find direct or transitive dependencies."""
        import networkx as nx
        if node_id not in self._nx_graph:
            return []
        
        if transitive:
            try:
                descendant_ids = nx.descendants(self._nx_graph, node_id)
            except nx.NetworkXError:
                return []
        else:
            descendant_ids = set(self._nx_graph.successors(node_id))
            
        results = []
        for did in descendant_ids:
            if did in self.graph.nodes:
                results.append(self.graph.nodes[did])
        return results

    def apply_execution_report(self, report_data: List[Dict[str, Any]]) -> int:
        """Apply execution results from Karate JSON report to the graph."""
        from karate_graph_analyzer.parser.execution_parser import ExecutionReportParser
        parser = ExecutionReportParser(self.graph)
        return parser.apply_report_data(report_data)

    def process_execution_directory(self, directory_path: str) -> Dict[str, Any]:
        """Scan directory, apply all reports, and return AI-distilled summary.
        
        Args:
            directory_path: Path to Karate reports directory
            
        Returns:
            Distilled summary for AI
        """
        from karate_graph_analyzer.parser.execution_parser import ExecutionReportParser
        parser = ExecutionReportParser(self.graph)
        
        # 1. Scan directory
        report_files = parser.scan_directory(directory_path)
        
        # 2. Apply reports
        parser.apply_reports(report_files)
        
        # 3. Return AI summary
        return parser.get_ai_summary()

    def _propagate_execution_status(self):
        """Propagate status from Scenarios up to Features and Folders.
        Note: This is now handled by ExecutionReportParser.apply_report_data.
        """
        pass

    def query_dependencies(self, node_id: str, transitive: bool = True) -> List[Node]:
        """Query dependencies using cached NetworkX graph."""
        import networkx as nx
        
        # Check if node exists in the graph
        if node_id not in self.graph.nodes:
            return []
        
        if transitive:
            try:
                dependency_ids = nx.descendants(self._nx_graph, node_id)
            except nx.NetworkXError:
                return []
        else:
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
        project_roots: Dict[str, str] = {}
        for project in projects:
            builder = GraphBuilder()
            graph = builder.build_from_project(project)
            project_graphs[project.name] = graph
            project_roots[project.name] = project.root_path
        
        # Track components across projects
        # Key: (node_type, name) -> List[ComponentInstance]
        component_instances: Dict[tuple, List] = defaultdict(list)
        
        # Collect all WORKFLOW, API, PAGE and COMMON nodes from all projects
        for project_name, graph in project_graphs.items():
            for node_id, node in graph.nodes.items():
                # Only consider WORKFLOW, API, PAGE and COMMON nodes
                if node.type not in [NodeType.WORKFLOW, NodeType.API, NodeType.PAGE, NodeType.COMMON]:
                    continue
                
                # Create component key (type, stable project-relative identity)
                component_name = self._common_component_identity(
                    node, project_roots.get(project_name, "")
                )
                component_key = (node.type, component_name)
                
                # Create ComponentInstance
                instance = ComponentInstance(
                    project_name=project_name,
                    file_path=node.metadata.file_path or "",
                    node_id=node_id,
                )
                
                if not any(
                    existing.project_name == project_name
                    for existing in component_instances[component_key]
                ):
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

    def _common_component_identity(self, node: Node, project_root: str) -> str:
        """Return a cross-project identity for reusable components."""
        import os

        if node.type in [NodeType.WORKFLOW, NodeType.COMMON, NodeType.PAGE]:
            raw_path = node.metadata.file_path or node.name
            if raw_path and project_root:
                try:
                    abs_root = os.path.abspath(project_root)
                    abs_path = os.path.abspath(raw_path)
                    if abs_path.startswith(abs_root):
                        raw_path = os.path.relpath(abs_path, abs_root)
                except (OSError, ValueError):
                    pass
            normalized = raw_path.replace("\\", "/")
            parts = [part for part in normalized.split("/") if part]
            for anchor in ("common", "workflows", "workflow", "pages", "webPages"):
                if anchor in parts:
                    return "/".join(parts[parts.index(anchor):])
            return normalized

        return node.name

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
    def find_failure_hotspots(self, min_impact: int = 1):
        """
        Identify components causing high-volume test failures.
        Uses Impact Analysis (Dependents) to calculate score.
        """
        from collections import defaultdict
        
        # 1. Get all terminal nodes (Test Cases / Scenarios)
        terminal_nodes = [
            (nid, n) for nid, n in self.graph.nodes.items()
            if n.type in [NodeType.TEST_CASE, NodeType.SCENARIO]
        ]
        
        if not terminal_nodes:
            return []

        # 2. For each non-terminal node, calculate its blast radius
        hotspot_stats = {} # nid -> {failed: X, total: Y}
        
        for node_id, node in self.graph.nodes.items():
            if node.type in [NodeType.TEST_CASE, NodeType.SCENARIO]:
                continue # Terminals aren't hotspots
            
            # Use impact_analysis to find all nodes that rely on this node
            impact_result = self.impact_analysis(node_id)
            affected_items = impact_result.affected_test_cases
            
            if not affected_items:
                continue
                
            total_affected = len(affected_items)
            failed_affected = 0
            affected_failed_test_cases = []
            
            for item in affected_items:
                # Retrieve original node to check status
                original_node = self.graph.nodes.get(item.node_id)
                if original_node and original_node.execution_status == "FAILED":
                    failed_affected += 1
                    affected_failed_test_cases.append({
                        "node_id": original_node.id,
                        "name": original_node.name,
                        "jira_tags": original_node.metadata.jira_tags,
                        "file_path": original_node.metadata.file_path,
                        "line_number": item.line_number,
                        "dependency_path": item.dependency_path,
                        "depth": item.depth,
                    })
            
            if failed_affected >= min_impact:
                hotspot_stats[node_id] = {
                    "failed": failed_affected,
                    "total": total_affected,
                    "name": node.name,
                    "type": node.type.value,
                    "affected_failed_test_cases": affected_failed_test_cases,
                }

        # 3. Build results
        results = []
        for node_id, stats in hotspot_stats.items():
            fail_percent = round((stats["failed"] / stats["total"]) * 100) if stats["total"] > 0 else 0
            
            results.append({
                "node_id": node_id,
                "name": stats["name"],
                "failure_impact_score": stats["failed"],
                "total_test_cases": stats["total"],
                "failed_test_cases": stats["failed"],
                "affected_failed_test_cases": stats["affected_failed_test_cases"],
                "failure_percentage": fail_percent,
                "type": stats["type"]
            })
            
        results.sort(key=lambda x: (x["failure_impact_score"], x["failure_percentage"]), reverse=True)
        return results

    def get_subgraph(self, node_id: str, radius: int = 2) -> Dict[str, Any]:
        """Extract a local subgraph around a node."""
        import networkx as nx
        if node_id not in self._nx_graph:
            return {"nodes": [], "edges": []}
            
        # Get nodes in neighborhood
        # Use undirected version to get both callers and callees
        undirected = self._nx_graph.to_undirected()
        try:
            ego = nx.ego_graph(undirected, node_id, radius=radius)
            neighborhood_nodes = set(ego.nodes())
        except nx.NetworkXError:
            neighborhood_nodes = {node_id}
            
        nodes_out = []
        for nid in neighborhood_nodes:
            if nid in self.graph.nodes:
                node = self.graph.nodes[nid]
                from dataclasses import asdict
                nodes_out.append({
                    "id": node.id,
                    "name": node.name,
                    "type": node.type.value,
                    "metadata": asdict(node.metadata)
                })
                
        edges_out = []
        for u, v, data in self._nx_graph.edges(data=True):
            if u in neighborhood_nodes and v in neighborhood_nodes:
                edges_out.append({
                    "from": u,
                    "to": v,
                    "type": data.get("type", "UNKNOWN")
                })
                
        return {"nodes": nodes_out, "edges": edges_out}

    def query_by_metadata(self, key: str, value: str) -> List[Node]:
        """Search nodes by metadata attributes."""
        results = []
        for node in self.graph.nodes.values():
            # Check additional_data
            if node.metadata.additional_data.get(key) == value:
                results.append(node)
                continue
            # Check direct attributes
            if hasattr(node.metadata, key) and getattr(node.metadata, key) == value:
                results.append(node)
                
        return results

    def find_paths(self, start_node_id: str, end_node_id: str) -> List[List[str]]:
        """Find all simple paths between two nodes."""
        import networkx as nx
        if start_node_id not in self._nx_graph or end_node_id not in self._nx_graph:
            return []
        
        try:
            # Limit to simple paths to avoid infinite loops and keep it efficient
            paths = list(nx.all_simple_paths(self._nx_graph, start_node_id, end_node_id, cutoff=10))
            return paths
        except nx.NetworkXError:
            return []

    def get_component_importance(self) -> List[Dict[str, Any]]:
        """Calculate node importance using degree centrality (in-degree).
        
        Nodes with high in-degree are 'huyết mạch' because many things depend on them.
        """
        import networkx as nx
        centrality = nx.in_degree_centrality(self._nx_graph)
        
        importance = []
        for nid, score in centrality.items():
            if score > 0:
                node = self.graph.nodes.get(nid)
                if node:
                    importance.append({
                        "id": nid,
                        "name": node.name,
                        "type": node.type.value,
                        "score": round(score * 100, 2)  # Percentage score
                    })
        
        # Sort by score descending
        return sorted(importance, key=lambda x: x["score"], reverse=True)

    def global_search(self, query: str) -> List[Node]:
        """Search across all node fields (name, id, metadata values)."""
        query = query.lower()
        results = []
        
        for node in self.graph.nodes.values():
            # Check basic fields
            if query in node.name.lower() or query in node.id.lower():
                results.append(node)
                continue
                
            # Check metadata fields
            meta_str = str(node.metadata).lower()
            if query in meta_str:
                results.append(node)
                continue
                
            # Check additional data
            add_data_str = str(node.metadata.additional_data).lower()
            if query in add_data_str:
                results.append(node)
                
        return results
