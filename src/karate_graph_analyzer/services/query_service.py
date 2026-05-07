"""
Graph query service.
"""

from typing import Callable, Dict, List, Optional

from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer


class QueryService:
    """Execute cross-project graph queries using analyzers."""

    def find_analyzer_for_node(
        self,
        analyzers: Dict[str, DependencyAnalyzer],
        node_id: str,
    ) -> Optional[DependencyAnalyzer]:
        for analyzer in analyzers.values():
            if node_id in analyzer.graph.nodes:
                return analyzer
        return None

    def collect_cross_project_results(
        self,
        analyzers: Dict[str, DependencyAnalyzer],
        query_fn: Callable[[DependencyAnalyzer], List[dict]],
    ) -> List[dict]:
        results: List[dict] = []
        for analyzer in analyzers.values():
            results.extend(query_fn(analyzer))
        return results
