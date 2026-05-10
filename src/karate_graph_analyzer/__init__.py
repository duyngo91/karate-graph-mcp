"""
Karate Feature Graph Analyzer

A Python-based MCP tool that analyzes Karate Framework feature files and generates
interactive dependency graphs for impact analysis and code reuse identification.
"""

try:
    from importlib.metadata import version as _pkg_version
except ImportError:  # pragma: no cover
    from importlib_metadata import version as _pkg_version  # type: ignore

try:
    __version__ = _pkg_version("karate-graph")
except Exception:  # pragma: no cover
    __version__ = "0.0.0"

from karate_graph_analyzer.models import (
    AffectedTestCase,
    ComponentInstance,
    Dependency,
    DependencyGraph,
    DependencyType,
    Edge,
    ImpactResult,
    Node,
    NodeMetadata,
    NodeType,
    ParserConfig,
    Project,
    ReusableComponent,
    Scenario,
    ScenarioType,
)

__all__ = [
    "__version__",
    "AffectedTestCase",
    "ComponentInstance",
    "Dependency",
    "DependencyGraph",
    "DependencyType",
    "Edge",
    "ImpactResult",
    "Node",
    "NodeMetadata",
    "NodeType",
    "ParserConfig",
    "Project",
    "ReusableComponent",
    "Scenario",
    "ScenarioType",
]
