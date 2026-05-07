"""
Reporting and visualization service.
"""

from pathlib import Path
from typing import Optional

from karate_graph_analyzer.analyzer.graph_diff import GraphComparator
from karate_graph_analyzer.models import DependencyGraph, VisualizationMode
from karate_graph_analyzer.visualization.graph_visualizer import GraphVisualizer


class ReportService:
    """Build visualization and diff reports for graphs."""

    def render_graph(
        self,
        graph: DependencyGraph,
        output_path: str,
        mode: Optional[VisualizationMode] = None,
    ) -> str:
        resolved_mode = mode or self._detect_mode(graph)
        visualizer = GraphVisualizer(graph, mode=resolved_mode)
        return visualizer.render(output_path=output_path)

    def render_diff(
        self,
        base_graph: DependencyGraph,
        new_graph: DependencyGraph,
        output_path: str,
    ) -> str:
        diff_graph = GraphComparator().compare(base_graph, new_graph)
        visualizer = GraphVisualizer(diff_graph, mode=VisualizationMode.DIFF)
        return visualizer.render(output_path=output_path)

    def build_timestamped_output_path(self, prefix: str, *parts: str) -> str:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = "_".join(parts)
        return str(Path("output") / f"{prefix}_{slug}_{timestamp}.html")

    def _detect_mode(self, graph: DependencyGraph) -> VisualizationMode:
        if any(node.execution_status for node in graph.nodes.values()):
            return VisualizationMode.EXECUTION
        return VisualizationMode.DEFAULT
