"""
Project management service.

Encapsulates project registration, listing, and analysis orchestration.
Extracted from KarateGraphAnalyzerTool (Facade Pattern).
"""

import logging
from typing import Any, Dict, List, Optional

from karate_graph_analyzer.cache.cache_manager import CacheManager
from karate_graph_analyzer.graph.graph_builder import GraphBuilder
from karate_graph_analyzer.models import (
    DependencyGraph,
    ParserConfig,
    Project,
)
from karate_graph_analyzer.storage.project_registry import ProjectRegistry

logger = logging.getLogger(__name__)


class ProjectService:
    """Manages project lifecycle: register, analyze, list.

    This service encapsulates the project management logic that was previously
    embedded in KarateGraphAnalyzerTool. It coordinates between the
    ProjectRegistry (persistence), GraphBuilder (analysis), and CacheManager.
    """

    def __init__(
        self,
        registry: ProjectRegistry,
        cache_manager: CacheManager,
    ) -> None:
        """Initialize project service.

        Args:
            registry: Project persistence layer
            cache_manager: AST cache for incremental parsing
        """
        self.registry = registry
        self.cache_manager = cache_manager
        self.graphs: Dict[str, DependencyGraph] = {}

    def register(
        self,
        name: str,
        root_path: str,
        feature_file_patterns: Optional[List[str]] = None,
        parser_config: Optional[ParserConfig] = None,
    ) -> Project:
        """Register a new Karate project.

        Args:
            name: Project name
            root_path: Root path of the project
            feature_file_patterns: Optional file glob patterns
            parser_config: Optional parser configuration

        Returns:
            Registered project

        Raises:
            ValueError: If project already exists or path is invalid
        """
        config = parser_config or ParserConfig()
        patterns = feature_file_patterns or ["**/*.feature"]

        project = Project(
            name=name,
            root_path=root_path,
            feature_file_patterns=patterns,
            parser_config=config,
        )

        self.registry.add(project)
        self.registry.save()

        logger.info(f"Registered project '{name}' at '{root_path}'")
        return project

    def analyze(self, project_name: str) -> DependencyGraph:
        """Analyze a project and build its dependency graph.

        Args:
            project_name: Name of registered project

        Returns:
            Built dependency graph

        Raises:
            KeyError: If project not found
        """
        project = self.registry.get(project_name)
        if project is None:
            raise KeyError(f"Project '{project_name}' not found")

        # Build graph
        builder = GraphBuilder()
        graph = builder.build_from_project(project)

        # Store graph
        self.graphs[project_name] = graph

        logger.info(
            f"Analyzed project '{project_name}': "
            f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )
        return graph

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all registered projects with summary info.

        Returns:
            List of project info dictionaries
        """
        projects = self.registry.list_all()
        return [
            {
                "name": p.name,
                "root_path": p.root_path,
                "feature_file_patterns": p.feature_file_patterns,
                "analyzed": p.name in self.graphs,
            }
            for p in projects
        ]
