"""
Dependency analyzer implementation.

Analyzes dependency graphs for impact and reusability.
"""

from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, deque

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
        self.outgoing: Dict[str, List[Tuple[str, Optional[int]]]] = {}
        self.incoming: Dict[str, List[Tuple[str, Optional[int]]]] = {}
        for edge in self.graph.edges.values():
            self._nx_graph.add_edge(
                edge.from_node, 
                edge.to_node, 
                id=edge.id, 
                type=edge.type,
                line_number=edge.line_number
            )
            self.outgoing.setdefault(edge.from_node, []).append((edge.to_node, edge.line_number))
            self.incoming.setdefault(edge.to_node, []).append((edge.from_node, edge.line_number))

        # Initialize expert analyzer
        from karate_graph_analyzer.analyzer.analysis_expert import AnalysisExpert
        self.expert = AnalysisExpert(self.graph, self._nx_graph)
        
        # Initialize fix expert
        from karate_graph_analyzer.analyzer.fix_expert import FixExpert
        self.fix_expert = FixExpert()

        # Initialize healer expert (AI Smart Suggestions)
        from karate_graph_analyzer.analyzer.healer_expert import HealerExpert
        self.healer_expert = HealerExpert(self.graph)

    def get_smart_fix_suggestion(self, node_id: str, error_message: str, project_root: str) -> Dict[str, Any]:
        """Get AI-powered smart fix suggestion for a failure."""
        return self.healer_expert.suggest_fix(node_id, error_message, project_root)

    def impact_analysis(self, component_id: str) -> ImpactResult:
        """Find all test cases affected by component change.

        Args:
            component_id: ID of the changed component

        Returns:
            ImpactResult with affected test cases, dependency paths, depths
        """
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

        affected_test_cases = []
        for ancestor_id, path, first_line in self._reverse_shortest_paths_to(component_id):
            node = self.graph.nodes[ancestor_id]
            if node.type not in [NodeType.TEST_CASE, NodeType.SCENARIO]:
                continue

            # Create AffectedTestCase object
            affected_test_case = AffectedTestCase(
                node_id=node.id,
                name=node.name,
                jira_tags=node.metadata.jira_tags,
                dependency_path=path,
                depth=len(path) - 1,
                line_number=first_line or node.metadata.line_number,
            )
            affected_test_cases.append(affected_test_case)
        
        # Return ImpactResult
        return ImpactResult(
            changed_component=component_id,
            affected_test_cases=affected_test_cases,
            total_count=len(affected_test_cases),
        )

    def _reverse_shortest_paths_to(self, component_id: str) -> List[Tuple[str, List[str], Optional[int]]]:
        """Return shortest caller paths to component using one reverse BFS."""
        results: List[Tuple[str, List[str], Optional[int]]] = []
        seen = {component_id}
        queue = deque([(component_id, [component_id], None)])

        while queue:
            current_id, reverse_path, first_line = queue.popleft()
            for parent_id, line_number in self.incoming.get(current_id, []):
                if parent_id in seen:
                    continue
                seen.add(parent_id)
                path = [parent_id] + reverse_path
                node = self.graph.nodes.get(parent_id)
                if node is not None:
                    edge_line = line_number if line_number is not None else first_line
                    results.append((parent_id, path, edge_line))
                queue.append((parent_id, path, edge_line))

        return results

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

    def apply_execution_report(
        self,
        report_data: List[Dict[str, Any]],
        run_context: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Apply execution results from Karate JSON report to the graph."""
        from karate_graph_analyzer.parser.execution_parser import ExecutionReportParser
        parser = ExecutionReportParser(self.graph, run_context=run_context)
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
        
        # Collect reusable nodes from all projects
        for project_name, graph in project_graphs.items():
            for node_id, node in graph.nodes.items():
                if node.type not in [
                    NodeType.WORKFLOW,
                    NodeType.API,
                    NodeType.PAGE,
                    NodeType.COMMON,
                    NodeType.JAVASCRIPT,
                    NodeType.JS_FUNCTION,
                ]:
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

        if node.type in [NodeType.WORKFLOW, NodeType.COMMON, NodeType.PAGE, NodeType.JAVASCRIPT]:
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
        from karate_graph_analyzer.graph.graph_query import GraphQuery

        failed_terminals = [
            node for node in self.graph.nodes.values()
            if node.type in [NodeType.TEST_CASE, NodeType.SCENARIO]
            and node.execution_status == "FAILED"
        ]

        if not failed_terminals:
            return []

        hotspot_stats: Dict[str, Dict[str, Any]] = {}
        for terminal in failed_terminals:
            queue = deque([(terminal.id, [terminal.id], terminal.metadata.line_number)])
            seen = {terminal.id}
            while queue:
                current_id, path, first_line = queue.popleft()
                for target_id, line_number in self.outgoing.get(current_id, []):
                    if target_id in seen:
                        continue
                    seen.add(target_id)
                    target = self.graph.nodes.get(target_id)
                    if not target:
                        continue
                    next_path = path + [target_id]
                    next_line = first_line or line_number
                    if target.type not in [NodeType.TEST_CASE, NodeType.SCENARIO]:
                        stats = hotspot_stats.setdefault(
                            target_id,
                            {
                                "failed": 0,
                                "name": target.name,
                                "type": target.type.value,
                                "affected_failed_test_cases": [],
                            },
                        )
                        stats["failed"] += 1
                        stats["affected_failed_test_cases"].append(
                            {
                                "node_id": terminal.id,
                                "name": terminal.name,
                                "jira_tags": terminal.metadata.jira_tags,
                                "file_path": terminal.metadata.file_path,
                                "line_number": next_line,
                                "dependency_path": next_path,
                                "depth": len(next_path) - 1,
                            }
                        )
                    queue.append((target_id, next_path, next_line))

        # 3. Build results
        results = []
        query = GraphQuery(self.graph)
        query._build_usage_index()
        for node_id, stats in hotspot_stats.items():
            if stats["failed"] < min_impact:
                continue

            node = self.graph.nodes.get(node_id)
            total = query.get_usage_count(node) if node else stats["failed"]
            total = max(total, stats["failed"])
            fail_percent = round((stats["failed"] / total) * 100) if total > 0 else 0
            
            results.append({
                "node_id": node_id,
                "name": stats["name"],
                "failure_impact_score": stats["failed"],
                "total_test_cases": total,
                "failed_test_cases": stats["failed"],
                "affected_failed_test_cases": stats["affected_failed_test_cases"],
                "failure_percentage": fail_percent,
                "type": stats["type"]
            })
            
        results.sort(key=lambda x: (x["failure_impact_score"], x["failure_percentage"]), reverse=True)
        return results

    def get_subgraph(self, node_id: str, radius: int = 2) -> Dict[str, Any]:
        """Extract a local subgraph around a node."""
        if node_id not in self.graph.nodes:
            return {"nodes": [], "edges": []}

        neighborhood_nodes = {node_id}
        frontier = {node_id}
        for _ in range(max(radius, 0)):
            next_frontier = set()
            for current_id in frontier:
                next_frontier.update(target for target, _ in self.outgoing.get(current_id, []))
                next_frontier.update(parent for parent, _ in self.incoming.get(current_id, []))
            next_frontier.difference_update(neighborhood_nodes)
            if not next_frontier:
                break
            neighborhood_nodes.update(next_frontier)
            frontier = next_frontier
            
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
        seen_edges = set()
        for u in neighborhood_nodes:
            for v, _ in self.outgoing.get(u, []):
                if v not in neighborhood_nodes:
                    continue
                data = self._nx_graph.get_edge_data(u, v, default={})
                edge_key = (u, v, data.get("id"))
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
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
        from itertools import islice
        import networkx as nx
        if start_node_id not in self._nx_graph or end_node_id not in self._nx_graph:
            return []
        
        try:
            # Limit to simple paths to avoid infinite loops and keep it efficient
            paths = list(islice(nx.all_simple_paths(self._nx_graph, start_node_id, end_node_id, cutoff=10), 50))
            return paths
        except nx.NetworkXError:
            return []

    def get_component_importance(self) -> List[Dict[str, Any]]:
        """Calculate node importance using degree centrality (in-degree).
        
        Nodes with high in-degree are 'huyết mạch' because many things depend on them.
        """
        importance = []
        denominator = max(len(self.graph.nodes) - 1, 1)
        for nid, incoming_edges in self.incoming.items():
            node = self.graph.nodes.get(nid)
            if node:
                importance.append({
                    "id": nid,
                    "name": node.name,
                    "type": node.type.value,
                    "score": round((len(incoming_edges) / denominator) * 100, 2)
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
