"""
Analysis service.

Encapsulates dependency analysis, impact analysis, and node queries.
Extracted from KarateGraphAnalyzerTool (Facade Pattern).
"""

import logging
from typing import Any, Dict, List, Optional

from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
from karate_graph_analyzer.models import DependencyGraph, ImpactResult

logger = logging.getLogger(__name__)


class AnalysisService:
    """Manages graph analysis operations.

    Provides impact analysis, dependency queries, and node details
    for analyzed project graphs.
    """

    def __init__(self) -> None:
        """Initialize analysis service."""
        self.graphs: Dict[str, DependencyGraph] = {}
        self.analyzers: Dict[str, DependencyAnalyzer] = {}

    def update_graph(self, project_name: str, graph: DependencyGraph) -> None:
        """Update the stored graph and create/refresh analyzer.

        Args:
            project_name: Project name
            graph: New dependency graph
        """
        self.graphs[project_name] = graph
        self.analyzers[project_name] = DependencyAnalyzer(graph)

    def impact_analysis(
        self, component_id: str, project_name: Optional[str] = None
    ) -> Optional[ImpactResult]:
        """Perform impact analysis for a component.

        Args:
            component_id: ID of the component to analyze
            project_name: Optional project name to scope the analysis

        Returns:
            ImpactResult or None if component not found
        """
        analyzer = self._find_analyzer(component_id, project_name)
        if analyzer is None:
            return None

        return analyzer.impact_analysis(component_id)

    def query_dependencies(
        self,
        node_id: str,
        transitive: bool = False,
        project_name: Optional[str] = None,
    ) -> Optional[List[str]]:
        """Query dependencies for a node.

        Args:
            node_id: Node ID to query
            transitive: If True, include transitive dependencies
            project_name: Optional project scope

        Returns:
            List of dependency node IDs, or None if not found
        """
        analyzer = self._find_analyzer(node_id, project_name)
        if analyzer is None:
            return None

        return analyzer.find_dependencies(node_id, transitive=transitive)

    def get_node_details(
        self, node_id: str, project_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get detailed information about a node.

        Args:
            node_id: Node ID
            project_name: Optional project scope

        Returns:
            Node details dictionary or None
        """
        # Search across all graphs
        for pname, graph in self.graphs.items():
            if project_name and pname != project_name:
                continue
            if node_id in graph.nodes:
                node = graph.nodes[node_id]
                return {
                    "id": node.id,
                    "type": node.type.value,
                    "name": node.name,
                    "metadata": {
                        "file_path": node.metadata.file_path,
                        "line_number": node.metadata.line_number,
                        "jira_tags": node.metadata.jira_tags,
                        "project_name": node.metadata.project_name,
                        "additional_data": node.metadata.additional_data,
                    },
                }
        return None

    def _find_analyzer(
        self, node_id: str, project_name: Optional[str] = None
    ) -> Optional[DependencyAnalyzer]:
        """Find the analyzer that contains the specified node.

        Args:
            node_id: Node ID to search for
            project_name: Optional project scope

        Returns:
            DependencyAnalyzer or None
        """
        if project_name:
            return self.analyzers.get(project_name)

        # Search across all analyzers
        for pname, graph in self.graphs.items():
            if node_id in graph.nodes:
                return self.analyzers.get(pname)

        return None
