"""
Project lifecycle service.
"""

from typing import Tuple

from karate_graph_analyzer.graph.graph_builder import GraphBuilder
from karate_graph_analyzer.models import DependencyGraph, Project
from karate_graph_analyzer.cache.cache_manager import CacheManager
from karate_graph_analyzer.services.graph_cache_service import GraphCacheService
from karate_graph_analyzer.storage.project_registry import ProjectRegistry


class ProjectLifecycleService:
    """Handle project-level analysis lifecycle with cache-aware loading."""

    def __init__(
        self,
        registry: ProjectRegistry,
        graph_cache: GraphCacheService,
        cache_manager: CacheManager,
    ) -> None:
        self.registry = registry
        self.graph_cache = graph_cache
        self.cache_manager = cache_manager

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

        builder = GraphBuilder(include_structural_nodes=include_structural_nodes)
        if getattr(project.parser_config, "incremental_scan_enabled", True):
            baseline = self.graph_cache.load_any(project)
            if baseline is not None:
                graph = builder.update_from_project(project, baseline, self.cache_manager)
                self.graph_cache.save_project_graph(project, graph, include_structural_nodes)
                return graph, False

        graph = builder.build_from_project(project)
        self.graph_cache.save_project_graph(project, graph, include_structural_nodes)
        return graph, False
