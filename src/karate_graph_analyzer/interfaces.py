"""
Abstract interfaces for Karate Graph Analyzer.

Defines contracts between layers using ABC (Abstract Base Classes).
This enables loose coupling, easy testing, and swappable implementations.

Design Patterns:
    - Interface Segregation Principle (ISP)
    - Dependency Inversion Principle (DIP)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from karate_graph_analyzer.models import (
    Dependency,
    DependencyGraph,
    FeatureAST,
    ParserConfig,
    Project,
)


# =============================================================================
# Strategy Pattern — Dependency Extractors
# =============================================================================


class IDependencyExtractor(ABC):
    """Interface for dependency extraction strategies.

    Each extractor handles one type of dependency (call read, API, database).
    New extractors can be added without modifying the parser (Open/Closed Principle).
    """

    @abstractmethod
    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        """Extract dependencies from a step text.

        Args:
            step_text: The text of a Gherkin step
            line_number: Line number in the feature file

        Returns:
            List of extracted dependencies
        """
        ...

    @abstractmethod
    def can_extract(self, step_text: str) -> bool:
        """Check if this extractor can handle the given step text.

        Args:
            step_text: The text of a Gherkin step

        Returns:
            True if this extractor should process the step
        """
        ...


# =============================================================================
# Strategy Pattern — Graph Export/Import
# =============================================================================


class IGraphExporter(ABC):
    """Interface for graph serialization strategies.

    Supports export and import of DependencyGraph in various formats.
    """

    @abstractmethod
    def export(self, graph: DependencyGraph) -> str:
        """Export a dependency graph to string format.

        Args:
            graph: The dependency graph to export

        Returns:
            Serialized string representation
        """
        ...

    @abstractmethod
    def import_graph(self, data: str, project_name: str) -> DependencyGraph:
        """Import a dependency graph from string format.

        Args:
            data: Serialized graph data
            project_name: Name for the imported project

        Returns:
            Reconstructed DependencyGraph
        """
        ...


# =============================================================================
# Repository Pattern — Project Storage
# =============================================================================


class IProjectRepository(ABC):
    """Interface for project persistence.

    Abstracts storage mechanism (JSON file, SQLite, Neo4j, etc.).
    """

    @abstractmethod
    def add(self, project: Project) -> None:
        """Add a project to the repository.

        Args:
            project: Project to add

        Raises:
            ValueError: If project with same name already exists
        """
        ...

    @abstractmethod
    def remove(self, project_name: str) -> None:
        """Remove a project from the repository.

        Args:
            project_name: Name of the project to remove

        Raises:
            KeyError: If project does not exist
        """
        ...

    @abstractmethod
    def get(self, project_name: str) -> Optional[Project]:
        """Get a project by name.

        Args:
            project_name: Name of the project

        Returns:
            Project if found, None otherwise
        """
        ...

    @abstractmethod
    def list_all(self) -> List[Project]:
        """List all registered projects.

        Returns:
            List of all projects
        """
        ...

    @abstractmethod
    def save(self) -> None:
        """Persist current state to storage."""
        ...

    @abstractmethod
    def load(self) -> None:
        """Load state from storage."""
        ...


# =============================================================================
# Cache Interface
# =============================================================================


class ICache(ABC):
    """Interface for caching mechanism.

    Abstracts cache implementation (LRU, Redis, etc.).
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value if found and valid, None otherwise
        """
        ...

    @abstractmethod
    def put(self, key: str, value: Any) -> None:
        """Store value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        ...

    @abstractmethod
    def invalidate(self, key: str) -> None:
        """Invalidate a cache entry.

        Args:
            key: Cache key to invalidate
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear entire cache."""
        ...
