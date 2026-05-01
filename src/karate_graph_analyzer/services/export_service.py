"""
Export service.

Encapsulates graph export/import operations.
Delegates to ExporterFactory (Strategy + Factory Pattern).
"""

import logging
from typing import Any, Dict

from karate_graph_analyzer.exporters import ExporterFactory
from karate_graph_analyzer.models import DependencyGraph

logger = logging.getLogger(__name__)


class ExportService:
    """Manages graph export and import operations.

    Delegates to ExporterFactory for format-specific serialization.
    Supports JSON and GraphML out of the box, extensible via factory registration.
    """

    def export(self, graph: DependencyGraph, format: str) -> str:
        """Export a dependency graph to the specified format.

        Args:
            graph: Dependency graph to export
            format: Export format ('json', 'graphml')

        Returns:
            Serialized graph data

        Raises:
            ValueError: If format is not supported
        """
        exporter = ExporterFactory.create(format)
        result = exporter.export(graph)
        logger.info(
            f"Exported graph '{graph.project_name}' to {format}: "
            f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )
        return result

    def import_graph(
        self, data: str, format: str, project_name: str
    ) -> DependencyGraph:
        """Import a dependency graph from serialized data.

        Args:
            data: Serialized graph data
            format: Import format ('json', 'graphml')
            project_name: Project name for the imported graph

        Returns:
            Reconstructed DependencyGraph

        Raises:
            ValueError: If format is not supported or data is invalid
        """
        exporter = ExporterFactory.create(format)
        graph = exporter.import_graph(data, project_name)
        logger.info(
            f"Imported graph '{project_name}' from {format}: "
            f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )
        return graph

    @staticmethod
    def supported_formats() -> list:
        """Get list of supported export/import formats.

        Returns:
            List of format strings
        """
        return ExporterFactory.supported_formats()
