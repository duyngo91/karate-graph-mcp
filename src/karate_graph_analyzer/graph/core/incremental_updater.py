"""
Incremental graph updater.

The updater only re-parses changed/new files, reuses cached ASTs for unchanged
files, then rebuilds the graph from the complete AST set. This keeps the output
semantically equivalent to a full analysis while preserving the expensive parser
cache benefit.
"""

import glob
import logging
import os
from typing import TYPE_CHECKING, List

from karate_graph_analyzer.models import DependencyGraph, ParseError

if TYPE_CHECKING:
    from karate_graph_analyzer.cache.cache_manager import CacheManager
    from karate_graph_analyzer.models import FeatureAST, Project

logger = logging.getLogger(__name__)


class IncrementalUpdater:
    """Handles cache-aware graph updates."""

    def __init__(self, nx_builder, path_classifier, dependency_linker) -> None:
        self.nx_builder = nx_builder
        self.path_classifier = path_classifier
        self.dependency_linker = dependency_linker

    def update_from_project(
        self,
        project: "Project",
        existing_graph: DependencyGraph,
        cache_manager: "CacheManager",
        parser,
    ) -> DependencyGraph:
        """Update the graph using cached ASTs for unchanged feature files."""
        feature_files = self._get_feature_files(project)
        current_files = set(feature_files)
        root = os.path.abspath(project.root_path)
        existing_files = {
            node.metadata.file_path
            for node in existing_graph.nodes.values()
            if node.metadata.file_path
            and os.path.isabs(node.metadata.file_path)
            and os.path.abspath(node.metadata.file_path).startswith(root)
        }
        deleted_files = {path for path in existing_files if path not in current_files}

        file_asts: List["FeatureAST"] = []
        changed_files = []

        for file_path in feature_files:
            cached_ast = cache_manager.get(file_path)
            if cached_ast is not None:
                file_asts.append(cached_ast)
                continue

            changed_files.append(file_path)
            try:
                ast = parser.parse_file(file_path)
                cache_manager.put(file_path, ast)
                file_asts.append(ast)
            except ParseError as e:
                logger.error("Failed to parse %s: %s", file_path, e)
            except Exception as e:
                logger.error("Unexpected error processing %s: %s", file_path, e, exc_info=True)

        for file_path in deleted_files:
            cache_manager.invalidate(file_path)

        if not changed_files and not deleted_files:
            logger.info("No file changes detected for project '%s'", project.name)
            return existing_graph

        logger.info(
            "Detected %d changed/new and %d deleted files in project '%s'",
            len(changed_files),
            len(deleted_files),
            project.name,
        )

        from karate_graph_analyzer.graph.graph_builder import GraphBuilder

        return GraphBuilder(parser=parser).build_from_asts(project, file_asts)

    def _get_feature_files(self, project: "Project") -> List[str]:
        feature_files = []
        for pattern in project.feature_file_patterns:
            full_pattern = os.path.join(project.root_path, pattern)
            feature_files.extend(glob.glob(full_pattern, recursive=True))
        return sorted(set(feature_files))
