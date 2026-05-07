"""
Project lifecycle service.
"""

from typing import Tuple

from karate_graph_analyzer.graph.graph_builder import GraphBuilder
from karate_graph_analyzer.models import DependencyGraph, Project
from karate_graph_analyzer.services.graph_cache_service import GraphCacheService
from karate_graph_analyzer.storage.project_registry import ProjectRegistry


class ProjectLifecycleService:
    """Handle project-level analysis lifecycle with cache-aware loading."""

    def __init__(self, registry: ProjectRegistry, graph_cache: GraphCacheService) -> None:
        self.registry = registry
        self.graph_cache = graph_cache

    def analyze(
        self, project_name: str, include_structural_nodes: bool = False
    ) -> Tuple[Project, DependencyGraph, bool]:
        """Analyze a registered project and return project, graph, cached flag."""
        project = self.registry.get(project_name)
        if project is None:
            raise KeyError(f"Project '{project_name}' not found in registry")

        graph, was_cached = self.load_or_build(project, include_structural_nodes)
        return project, graph, was_cached

    def load_or_build(
        self, project: Project, include_structural_nodes: bool = False
    ) -> Tuple[DependencyGraph, bool]:
        """Load a fresh-enough cached graph or build a new one."""
        graph = self.graph_cache.load_if_fresh(project, include_structural_nodes)
        if graph:
            return graph, True

        graph = GraphBuilder(
            include_structural_nodes=include_structural_nodes
        ).build_from_project(project)
        self.graph_cache.save_project_graph(project, graph, include_structural_nodes)
        return graph, False
