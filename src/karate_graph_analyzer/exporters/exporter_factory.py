"""
Exporter factory.

Factory Pattern for creating graph exporters by format name.
Supports registration of custom exporters (Open/Closed Principle).
"""

from typing import Dict, Type

from karate_graph_analyzer.interfaces import IGraphExporter


class ExporterFactory:
    """Factory for creating graph exporters by format string.

    Supports:
    - Built-in formats: 'json', 'graphml'
    - Custom format registration via register() method

    Example:
        exporter = ExporterFactory.create("json")
        data = exporter.export(graph)

        # Register custom exporter
        ExporterFactory.register("cypher", CypherExporter)
    """

    _exporters: Dict[str, Type[IGraphExporter]] = {}

    @classmethod
    def _ensure_defaults(cls) -> None:
        """Ensure default exporters are registered (lazy initialization)."""
        if not cls._exporters:
            from karate_graph_analyzer.exporters.json_exporter import JsonExporter
            from karate_graph_analyzer.exporters.graphml_exporter import GraphMLExporter

            cls._exporters = {
                "json": JsonExporter,
                "graphml": GraphMLExporter,
            }

    @classmethod
    def create(cls, format: str) -> IGraphExporter:
        """Create an exporter for the specified format.

        Args:
            format: Export format string (e.g., 'json', 'graphml')

        Returns:
            IGraphExporter instance

        Raises:
            ValueError: If format is not supported
        """
        cls._ensure_defaults()
        format_lower = format.lower()

        if format_lower not in cls._exporters:
            supported = ", ".join(sorted(cls._exporters.keys()))
            raise ValueError(
                f"Unsupported format: '{format}'. Supported formats: {supported}"
            )

        return cls._exporters[format_lower]()

    @classmethod
    def register(cls, format: str, exporter_class: Type[IGraphExporter]) -> None:
        """Register a custom exporter for a format.

        Allows extending the factory with new formats without modifying
        existing code (Open/Closed Principle).

        Args:
            format: Format string identifier
            exporter_class: Class implementing IGraphExporter
        """
        cls._ensure_defaults()
        cls._exporters[format.lower()] = exporter_class

    @classmethod
    def supported_formats(cls) -> list:
        """Get list of supported export formats.

        Returns:
            List of format strings
        """
        cls._ensure_defaults()
        return sorted(cls._exporters.keys())
