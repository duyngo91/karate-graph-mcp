"""In-memory runtime graph and analyzer store."""

from typing import Dict, Optional

from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
from karate_graph_analyzer.models import DependencyGraph


class RuntimeGraphStore:
    """Manage runtime graph/analyzer state for analyzed projects."""

    def __init__(self) -> None:
        self.graphs: Dict[str, DependencyGraph] = {}
        self.analyzers: Dict[str, DependencyAnalyzer] = {}

    def put(self, project_name: str, graph: DependencyGraph) -> None:
        self.graphs[project_name] = graph
        self.analyzers[project_name] = DependencyAnalyzer(graph)

    def get_graph(self, project_name: str) -> Optional[DependencyGraph]:
        return self.graphs.get(project_name)

    def get_analyzer(self, project_name: str) -> Optional[DependencyAnalyzer]:
        return self.analyzers.get(project_name)

    def find_analyzer_for_node(self, node_id: str) -> Optional[DependencyAnalyzer]:
        for analyzer in self.analyzers.values():
            if node_id in analyzer.graph.nodes:
                return analyzer
        return None

    def remove(self, project_name: str) -> None:
        self.graphs.pop(project_name, None)
        self.analyzers.pop(project_name, None)

    def clear(self) -> None:
        self.graphs.clear()
        self.analyzers.clear()
