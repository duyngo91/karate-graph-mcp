"""
MCP tool interface implementation.

Provides MCP protocol interface for graph analyzer.
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import networkx as nx

from pydantic import BaseModel, Field, field_validator

from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
from karate_graph_analyzer.cache.cache_manager import CacheManager
from karate_graph_analyzer.exporters import ExporterFactory
from karate_graph_analyzer.mcp_interface.responses import error_response
from karate_graph_analyzer.mcp_interface.search_tools import SearchTools
from karate_graph_analyzer.services.graph_cache_service import GraphCacheService
<<<<<<< Updated upstream
=======
from karate_graph_analyzer.services.fix_priority_service import FixPriorityService
from karate_graph_analyzer.services.db_tracking_service import DbTrackingService
from karate_graph_analyzer.services.feature_understanding_service import FeatureUnderstandingService
>>>>>>> Stashed changes
from karate_graph_analyzer.services.failure_context_service import FailureContextService
from karate_graph_analyzer.services.project_lifecycle_service import ProjectLifecycleService
from karate_graph_analyzer.services.query_service import QueryService
from karate_graph_analyzer.services.report_service import ReportService
from karate_graph_analyzer.services.reusable_function_search_service import (
    ReusableFunctionSearchService,
)
from karate_graph_analyzer.services.runtime_graph_store import RuntimeGraphStore
from karate_graph_analyzer.models import (
    DependencyGraph,
    ImpactResult,
    NodeType,
    ParserConfig,
    Project,
    ReusableComponent,
    VisualizationMode,
)
from karate_graph_analyzer.storage.project_registry import ProjectRegistry
from karate_graph_analyzer.utils.source_snippet import get_source_snippet

logger = logging.getLogger(__name__)


# Pydantic models for input validation
class RegisterProjectRequest(BaseModel):
    """Request model for register_project."""

    name: str = Field(..., min_length=1, description="Project name")
    root_path: str = Field(..., min_length=1, description="Root path of the project")
    feature_file_patterns: Optional[List[str]] = Field(
        default=None, description="Feature file glob patterns"
    )
    parser_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Parser configuration"
    )


class AnalyzeProjectRequest(BaseModel):
    """Request model for analyze_project."""

    project_name: str = Field(..., min_length=1, description="Name of the project to analyze")
    include_structural_nodes: bool = Field(
        default=False, description="Whether to include folder/file structural nodes"
    )


class QueryDependenciesRequest(BaseModel):
    """Request model for query_dependencies."""

    component_id: str = Field(..., min_length=1, description="Component identifier")
    transitive: bool = Field(default=True, description="Include transitive dependencies")


class ImpactAnalysisRequest(BaseModel):
    """Request model for impact_analysis."""

    component_id: str = Field(..., min_length=1, description="Component identifier")


class GetNodeDetailsRequest(BaseModel):
    """Request model for get_node_details."""

    node_id: str = Field(..., min_length=1, description="Node identifier")


class FindCommonComponentsRequest(BaseModel):
    """Request model for find_common_components."""

    project_names: List[str] = Field(..., min_length=1, description="List of project names")


class ExportGraphRequest(BaseModel):
    """Request model for export_graph."""

    project_name: str = Field(..., min_length=1, description="Project name")
    format: str = Field(..., description="Export format")

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate export format."""
        if v.lower() not in ["json", "graphml"]:
            raise ValueError("Format must be 'json' or 'graphml'")
        return v.lower()


class ImportGraphRequest(BaseModel):
    """Request model for import_graph."""

    data: str = Field(..., min_length=1, description="Graph data string")
    format: str = Field(..., description="Import format")
    project_name: str = Field(..., min_length=1, description="Project name for imported graph")

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate import format."""
        if v.lower() not in ["json", "graphml"]:
            raise ValueError("Format must be 'json' or 'graphml'")
        return v.lower()


class MergeProjectsRequest(BaseModel):
    """Request model for merge_projects."""

    project_names: List[str] = Field(..., min_length=1, description="List of project names to merge")
    new_project_name: str = Field(default="Merged_Project", description="Name for the resulting merged project")


class ProcessReportsFolderRequest(BaseModel):
    """Request model for process_reports_folder."""

    project_name: str = Field(..., description="Name of the analyzed project")
    directory_path: str = Field(..., description="Path to the directory containing Karate JSON reports")
    output_path: Optional[str] = Field(default=None, description="Optional custom path to save the HTML file")


class RenderExecutionReportRequest(BaseModel):
    """Request model for render_execution_report."""

    project_name: str = Field(..., description="Name of the analyzed project")
    report_path: str = Field(..., description="Path to the Karate execution report (JSON format)")
    output_path: Optional[str] = Field(default=None, description="Optional custom path to save the HTML file")


class CompareProjectsRequest(BaseModel):
    """Request model for compare_projects."""

    base_project_name: str = Field(..., description="Name of the base (old) project")
    new_project_name: str = Field(..., description="Name of the new project to compare")
    output_path: Optional[str] = Field(default=None, description="Optional custom path to save the HTML file")


class GetApiStatsRequest(BaseModel):
    """Request model for get_api_stats."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    keyword: Optional[str] = Field(default=None, description="Optional keyword to filter APIs (in domain or path)")


class GetPageStatsRequest(BaseModel):
    """Request model for get_page_stats."""

    domain: Optional[str] = Field(default=None, description="Optional business domain to filter pages (e.g. 'Authentication')")


class DeleteProjectRequest(BaseModel):
    """Request model for delete_project."""

    project_name: str = Field(..., min_length=1, description="Name of the project to delete")


class GetSubgraphRequest(BaseModel):
    """Request model for get_subgraph."""
    node_id: str = Field(..., min_length=1, description="Target node ID")
    radius: int = Field(default=2, description="Number of hops to include")


class QueryNodeByMetadataRequest(BaseModel):
    """Request model for query_node_by_metadata."""
    key: str = Field(..., description="Metadata key to search in (e.g., 'feature', 'category')")
    value: str = Field(..., description="Value to match")


class GlobalSearchRequest(BaseModel):
    """Request model for global_search."""
    query: str = Field(..., description="Search query across all fields")


class FindPathRequest(BaseModel):
    """Request model for find_path."""
    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")


class ProjectOnlyRequest(BaseModel):
    """Request model for tools that only need a project name."""
    project_name: str = Field(..., description="Project name")


class QueryPresetRequest(BaseModel):
    """Request model for preset query shortcuts."""

    project_name: str = Field(..., min_length=1, description="Project name")
    limit: int = Field(default=10, ge=1, le=200, description="Max number of items")


class AutoFixHintPackRequest(BaseModel):
    """Request model for auto fix hint pack."""

    project_name: str = Field(..., min_length=1, description="Project name")
    node_id: str = Field(..., min_length=1, description="Failing node id")
    error_message: str = Field(..., min_length=1, description="Error message")
    max_historical: int = Field(
        default=3, ge=1, le=20, description="Max historical suggestions included"
    )


class FailureDebugContextRequest(BaseModel):
    """Request model for AI failure debug context."""

    project_name: str = Field(..., min_length=1, description="Name of the analyzed project")
    node_id: str = Field(..., min_length=1, description="Failing node id")
    error_message: Optional[str] = Field(default=None, description="Optional current error message override")
    radius: int = Field(default=2, ge=0, le=5, description="Dependency context radius")
    max_historical: int = Field(default=3, ge=0, le=20, description="Max historical fix hints")


class FailureHistoryRequest(BaseModel):
    """Request model for failure history lookup."""

    project_name: str = Field(..., min_length=1, description="Name of the analyzed project")
    node_id: str = Field(..., min_length=1, description="Node id")


class ChangeImpactPreviewRequest(BaseModel):
    """Request model for change impact preview."""

    project_name: str = Field(..., min_length=1, description="Name of the analyzed project")
    changed_paths: List[str] = Field(
        ..., min_length=1, description="List of changed file paths or path keywords"
    )
    limit: int = Field(default=50, ge=1, le=500, description="Max impacted test cases")


class TestSelectionSuggestionRequest(BaseModel):
    """Request model for suggested rerun test selection."""

    project_name: str = Field(..., min_length=1, description="Name of the analyzed project")
    changed_paths: List[str] = Field(
        ..., min_length=1, description="List of changed file paths or path keywords"
    )
    limit: int = Field(default=30, ge=1, le=500, description="Max suggested test cases")

<<<<<<< Updated upstream
=======

class FeatureIntentIndexRequest(BaseModel):
    """Request model for feature intent search/index."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    query: Optional[str] = Field(default=None, description="Optional intent keyword filter")
    limit: int = Field(default=100, ge=1, le=500, description="Max scenarios returned")


class FeatureScenarioSelectorRequest(BaseModel):
    """Request model for selecting feature scenarios."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    feature_path: Optional[str] = Field(default=None, description="Feature path or path fragment")
    scenario_tag: Optional[str] = Field(default=None, description="Scenario tag, e.g. @TC-103")
    scenario_name: Optional[str] = Field(default=None, description="Scenario name fragment")
    node_id: Optional[str] = Field(default=None, description="Optional graph node id")
    limit: int = Field(default=50, ge=1, le=500, description="Max scenarios returned")


class AssertionMapRequest(BaseModel):
    """Request model for assertion map."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    query: Optional[str] = Field(default=None, description="Optional assertion keyword filter")
    limit: int = Field(default=100, ge=1, le=500, description="Max assertions returned")


class CallReadDeepContextRequest(FeatureScenarioSelectorRequest):
    """Request model for call-read deep context."""

    max_depth: int = Field(default=2, ge=0, le=5, description="Nested call/read depth")


class AiFeatureContextPackRequest(FeatureScenarioSelectorRequest):
    """Request model for AI feature context pack."""

    max_call_depth: int = Field(default=2, ge=0, le=5, description="Nested call/read depth")


class ScenarioSimilarityMapRequest(BaseModel):
    """Request model for scenario similarity mapping."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    query: Optional[str] = Field(default=None, description="Optional scenario keyword filter")
    limit: int = Field(default=50, ge=1, le=500, description="Max anchor scenarios returned")
    top_k: int = Field(default=3, ge=1, le=10, description="Max similar scenarios per anchor")


class FeatureReuseAdvisorRequest(BaseModel):
    """Request model for duplicate step/flow reuse advisor."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    min_group_size: int = Field(default=2, ge=2, le=50, description="Minimum duplicate locations")
    min_flow_length: int = Field(default=3, ge=2, le=10, description="Minimum duplicate flow length")
    limit: int = Field(default=50, ge=1, le=500, description="Max groups returned")
    include_low_signal: bool = Field(default=False, description="Include generic grammar steps")


class DbQueryIndexRequest(BaseModel):
    """Request model for database query/component index."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    query: Optional[str] = Field(default=None, description="Optional DB keyword filter")
    limit: int = Field(default=100, ge=1, le=500, description="Max items returned")
    include_components: bool = Field(
        default=True,
        description="Include DB components (feature files/executors) besides raw queries",
    )


class DbSearchUsageRequest(BaseModel):
    """Request model for searching DB usage."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    query: str = Field(..., min_length=1, description="DB keyword, table, operation, host, or file path")
    limit: int = Field(default=100, ge=1, le=500, description="Max results returned")


class DbScenarioTraceRequest(FeatureScenarioSelectorRequest):
    """Request model for DB data-flow traces by scenario selector."""


class DbImpactPreviewRequest(BaseModel):
    """Request model for DB impact preview from changed entities."""

    project_name: str = Field(..., min_length=1, description="Name of the project")
    changed_entities: List[str] = Field(
        ...,
        min_length=1,
        description="Changed DB entities such as tables, schemas, hosts, or DB feature paths",
    )
    limit: int = Field(default=50, ge=1, le=500, description="Max impacted test cases returned")


>>>>>>> Stashed changes
class KarateGraphAnalyzerTool:
    """MCP protocol interface for graph analyzer."""

    SEARCH_NOT_READY_ERROR = (
        7000,
        "SEARCH_ERROR",
        "No projects have been analyzed. Analyze a project first.",
    )

    PROJECT_NOT_FOUND_ERROR = (7001, "PROJECT_NOT_FOUND")
    PROJECT_NOT_ANALYZED_ERROR = (3003, "PROJECT_MANAGEMENT")

    def __init__(self, storage_path: str = ".karate_projects.json", storage_dir: Optional[str] = None) -> None:
        """Initialize MCP tool interface.

        Args:
            storage_path: Path to project registry storage file
            storage_dir: Optional directory for graph persistence
        """
        self.registry = ProjectRegistry(storage_path=storage_path)
        self.cache_manager = CacheManager()
        self.runtime_store = RuntimeGraphStore()
        # Backward-compatible aliases used by existing tests/integrations.
        self.graphs = self.runtime_store.graphs  # project_name -> graph
        self.analyzers = self.runtime_store.analyzers  # project_name -> analyzer
        self.search_tools: Optional[SearchTools] = None  # Initialized after first graph is loaded
        
        # Ensure storage directory for graphs exists
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            self.storage_dir = Path(".karate_cache") / "graphs"
            
        import os
        logger.info(f"KarateGraphAnalyzerTool initialized in CWD: {os.getcwd()}")
        logger.info(f"Using storage directory: {self.storage_dir.absolute()}")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.graph_cache = GraphCacheService(self.storage_dir)
        self.lifecycle_service = ProjectLifecycleService(self.registry, self.graph_cache)
        self.query_service = QueryService()
        self.report_service = ReportService()
        self.failure_context_service = FailureContextService()

        # Load existing projects from storage
        try:
            self.registry.load()
            logger.info(f"Loaded {len(self.registry.list())} projects from registry")
        except Exception as e:
            logger.warning(f"Failed to load project registry: {e}")

    def _ensure_search_tools(self) -> Optional[Dict[str, Any]]:
        """Return an error response if search tooling is unavailable."""
        if self.search_tools is None:
            if self.graphs:
                self._refresh_search_tools()
            
            if self.search_tools is None:
                return self._error_response(*self.SEARCH_NOT_READY_ERROR)
        return None

    def _get_analyzer(self, project_name: str) -> Optional[DependencyAnalyzer]:
        """Return analyzer for an analyzed project."""
        return self.runtime_store.get_analyzer(project_name)

    def _require_analyzer(self, project_name: str) -> Optional[Dict[str, Any]]:
        """Return an error response if the project has not been analyzed."""
        if self._get_analyzer(project_name) is None:
            return self._error_response(
                *self.PROJECT_NOT_FOUND_ERROR,
                f"Project '{project_name}' not found",
            )
        return None

    def _get_graph(self, project_name: str) -> Optional[DependencyGraph]:
        """Return graph for an analyzed project."""
        return self.runtime_store.get_graph(project_name)

    def _require_graph(
        self,
        project_name: str,
        message_template: str = "Project '{project_name}' has not been analyzed",
    ) -> Optional[Dict[str, Any]]:
        """Return an error response if the project graph is unavailable."""
        if self._get_graph(project_name) is None:
            return self._error_response(
                *self.PROJECT_NOT_ANALYZED_ERROR,
                message_template.format(project_name=project_name),
            )
        return None

    def _refresh_search_tools(self) -> None:
        """Initialize or refresh search tooling after graph changes."""
        if self.search_tools is None:
            if not self.graphs:
                return
            self.search_tools = SearchTools(self.graphs)
            return

        self.search_tools.graphs = self.graphs
        self.search_tools.query_apis.clear()

    def _store_runtime_graph(self, project_name: str, graph: DependencyGraph) -> None:
        """Store graph/analyzer state in memory and refresh search tooling."""
        self.runtime_store.put(project_name, graph)
        self._refresh_search_tools()

    def _remove_runtime_project(self, project_name: str) -> None:
        """Remove one project from in-memory state and refresh search tooling."""
        self.runtime_store.remove(project_name)
        path = self.storage_dir / f"{project_name}.json"
        if path.exists():
            path.unlink()
        self._refresh_search_tools()

    def _clear_runtime_projects(self) -> None:
        """Clear in-memory graph/analyzer state and refresh search tooling."""
        self.runtime_store.clear()
        self._refresh_search_tools()

    def _build_graph_statistics(self, graph: DependencyGraph) -> Dict[str, Any]:
        """Build standard graph statistics payload."""
        node_counts: Dict[str, int] = {}
        for node in graph.nodes.values():
            node_type = node.type.value
            node_counts[node_type] = node_counts.get(node_type, 0) + 1

        return {
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
            "node_counts": node_counts,
            "cycles_detected": len(graph.cycles),
        }

    def _load_or_build_project_graph(
        self, project: Project, include_structural_nodes: bool = False
    ) -> tuple[DependencyGraph, bool]:
        """Load a cached project graph or build and persist a fresh one."""
        return self.lifecycle_service.load_or_build(project, include_structural_nodes)

    def _resolve_project_visualization_path(
        self, project_name: str, output_path: Optional[str] = None
    ) -> str:
        """Resolve the output path for a project visualization."""
        if output_path:
            return output_path

        project = self.registry.get(project_name)
        if project:
            out_dir = Path(project.root_path) / "output"
            out_dir.mkdir(exist_ok=True)
            return str(out_dir / f"{project_name}_graph.html")

        return f"{project_name}_graph.html"

    def _resolve_timestamped_output_path(self, prefix: str, *parts: str) -> str:
        """Create a timestamped HTML output path under the local output folder."""
        return self.report_service.build_timestamped_output_path(prefix, *parts)

    def _render_graph_visualization(
        self,
        graph: DependencyGraph,
        mode: VisualizationMode,
        output_path: str,
    ) -> str:
        """Render a graph using the standard visualizer."""
        return self.report_service.render_graph(graph, output_path, mode)

    def _load_json_file(self, file_path: str) -> Any:
        """Load JSON content from disk."""
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_report_run_context(self, report_path: str) -> Dict[str, Any]:
        path = Path(report_path)
        applied_at = datetime.now(timezone.utc).isoformat()
        if path.exists():
            stat = path.stat()
            return {
                "run_id": f"{path.stem}:{stat.st_mtime_ns}",
                "report_path": str(path.resolve()),
                "report_file": path.name,
                "report_mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "applied_at": applied_at,
            }

        return {
            "run_id": f"{path.stem}:{applied_at}",
            "report_path": str(path),
            "report_file": path.name,
            "applied_at": applied_at,
        }

    def _serialize_node_metadata(self, node: Any) -> Dict[str, Any]:
        """Serialize node metadata in a consistent shape."""
        return {
            "file_path": node.metadata.file_path,
            "line_number": node.metadata.line_number,
            "jira_tags": node.metadata.jira_tags,
            "project_name": node.metadata.project_name,
        }

    def _serialize_node_summary(
        self,
        node: Any,
        *,
        include_metadata: bool = True,
        include_additional_data: bool = False,
        include_source_snippet: bool = False,
    ) -> Dict[str, Any]:
        """Serialize a node to response shape used by MCP query methods."""
        result = {
            "id": node.id,
            "type": node.type.value,
            "name": node.name,
        }

        if include_metadata:
            metadata = self._serialize_node_metadata(node)
            if include_source_snippet:
                metadata["source_snippet"] = get_source_snippet(
                    node.metadata.file_path, node.metadata.line_number
                )
            if include_additional_data:
                metadata["additional_data"] = node.metadata.additional_data
            result["metadata"] = metadata

        return result

    def _collect_cross_project_search_results(
        self, query_fn: Any
    ) -> List[Dict[str, Any]]:
        """Collect node search results from every analyzed project."""
        def _collect_for_analyzer(analyzer: DependencyAnalyzer) -> List[Dict[str, Any]]:
            project_name = analyzer.graph.project_name
            nodes = query_fn(analyzer)
            return [
                {
                    "id": node.id,
                    "type": node.type.value,
                    "name": node.name,
                    "project": project_name,
                    "metadata": asdict(node.metadata),
                }
                for node in nodes
            ]

        return self.query_service.collect_cross_project_results(
            self.analyzers, _collect_for_analyzer
        )

    def _with_search_tools(self, action: Any) -> Dict[str, Any]:
        """Execute a search action only when search tools are initialized."""
        search_error = self._ensure_search_tools()
        if search_error:
            return search_error
        return action(self.search_tools)

    def _with_query_api(self, project_name: str, action: Any) -> Dict[str, Any]:
        """Execute a low-level GraphQuery action with consistent project lookup."""
        def _action(tools: SearchTools) -> Dict[str, Any]:
            query_api = tools._get_query_api(project_name)
            if not query_api:
                return self._error_response(
                    3003, "PROJECT_MANAGEMENT", f"Project '{project_name}' not found"
                )
            return action(query_api)

        return self._with_search_tools(_action)

<<<<<<< Updated upstream
=======
    def _feature_understanding_service(
        self,
        project_name: str,
    ) -> tuple[Optional[FeatureUnderstandingService], Optional[Dict[str, Any]]]:
        project = self.registry.get(project_name)
        if not project:
            return None, self._error_response(
                3003,
                "PROJECT_MANAGEMENT",
                f"Project '{project_name}' not found in registry",
            )
        return FeatureUnderstandingService(project, self.graphs.get(project_name)), None

    def _db_tracking_service(
        self,
        project_name: str,
    ) -> tuple[Optional[DbTrackingService], Optional[Dict[str, Any]]]:
        project = self.registry.get(project_name)
        if not project:
            return None, self._error_response(
                3003,
                "PROJECT_MANAGEMENT",
                f"Project '{project_name}' not found in registry",
            )
        return DbTrackingService(project, self.graphs.get(project_name)), None

>>>>>>> Stashed changes
    def register_project(
        self,
        name: str,
        root_path: str,
        feature_file_patterns: Optional[List[str]] = None,
        parser_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register a new Karate project.

        Args:
            name: Project name
            root_path: Root path of the project
            feature_file_patterns: Optional feature file glob patterns
            parser_config: Optional parser configuration

        Returns:
            Result dictionary with success status
        """
        try:
            # Validate input using Pydantic
            request = RegisterProjectRequest(
                name=name,
                root_path=root_path,
                feature_file_patterns=feature_file_patterns,
                parser_config=parser_config,
            )

            # Create parser config
            config = ParserConfig()
            if parser_config:
                config = ParserConfig(**parser_config)
            else:
                from karate_graph_analyzer.parser.config_parser import KarateConfigParser
                config_parser = KarateConfigParser(root_path)
                config = config_parser.auto_configure()
                logger.info(f"Auto-detected configuration for project '{name}'")

            # Create project - Use broad pattern by default but exclude build artifacts
            patterns = feature_file_patterns or ["**/*.feature"]
            project = Project(
                name=request.name,
                root_path=request.root_path,
                feature_file_patterns=patterns,
                parser_config=config,
            )

            # Add to registry
            self.registry.add(project)

            # Persist registry
            self.registry.save()

            logger.info(f"Registered project '{name}' at path '{root_path}'")

            return {
                "success": True,
                "message": f"Project '{name}' registered successfully",
                "project": {
                    "name": project.name,
                    "root_path": project.root_path,
                    "feature_file_patterns": project.feature_file_patterns,
                },
            }

        except ValueError as e:
            logger.error(f"Failed to register project '{name}': {e}")
            return self._error_response(3001, "PROJECT_MANAGEMENT", str(e))
        except Exception as e:
            logger.error(f"Unexpected error registering project '{name}': {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def delete_project(self, name: str) -> Dict[str, Any]:
        """Delete a project from the registry.

        Args:
            name: Project name to delete

        Returns:
            Result dictionary with success status
        """
        try:
            # Validate input
            request = DeleteProjectRequest(project_name=name)

            # Check if project exists
            if not self.registry.get(request.project_name):
                return self._error_response(3003, "PROJECT_MANAGEMENT", f"Project '{name}' not found")

            # Remove from registry
            self.registry.remove(request.project_name)

            self._remove_runtime_project(request.project_name)

            logger.info(f"Deleted project '{name}'")

            return {
                "success": True,
                "message": f"Project '{name}' deleted successfully",
            }

        except Exception as e:
            logger.error(f"Failed to delete project '{name}': {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def clear_all_projects(self) -> Dict[str, Any]:
        """Clear all projects from the registry and memory.

        Returns:
            Result dictionary with success status
        """
        try:
            # Get all project names
            projects = self.registry.list()
            count = len(projects)

            # Clear registry
            for project in projects:
                self.registry.remove(project.name)

            self._clear_runtime_projects()
            
            # Clear on-disk cache
            self.cache_manager.clear()
            
            # Remove all saved graph JSON files
            import shutil
            if self.storage_dir.exists():
                shutil.rmtree(self.storage_dir)
                self.storage_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Cleared all {count} projects and cache")

            return {
                "success": True,
                "message": f"All {count} projects cleared successfully",
            }

        except Exception as e:
            logger.error(f"Failed to clear projects: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all registered projects.

        Returns:
            List of project information dictionaries
        """
        try:
            projects = self.registry.list()

            result = []
            for project in projects:
                result.append(
                    {
                        "name": project.name,
                        "root_path": project.root_path,
                        "feature_file_patterns": project.feature_file_patterns,
                        "analyzed": project.name in self.graphs,
                    }
                )

            logger.info(f"Listed {len(result)} projects")
            return result

        except Exception as e:
            logger.error(f"Failed to list projects: {e}")
            return [self._error_response(6003, "INTERNAL_ERROR", str(e))]

    def analyze_project(self, project_name: str, include_structural_nodes: bool = False) -> Dict[str, Any]:
        """Build dependency graph for project."""
        try:
            # Validate input
            request = AnalyzeProjectRequest(project_name=project_name, include_structural_nodes=include_structural_nodes)

            try:
                _, graph, was_cached = self.lifecycle_service.analyze(
                    request.project_name,
                    include_structural_nodes=request.include_structural_nodes,
                )
            except KeyError:
                return self._error_response(
                    3003,
                    "PROJECT_MANAGEMENT",
                    f"Project '{project_name}' not found in registry",
                )

            self._store_runtime_graph(project_name, graph)

            status_msg = "(Persistent State Loaded)" if was_cached else "(Freshly Analyzed)"
            logger.info(
                f"Analyzed project '{project_name}' {status_msg}: "
                f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
            )

            return {
                "success": True,
                "project_name": project_name,
                "message": f"Analysis completed for {project_name} {status_msg}",
                "statistics": self._build_graph_statistics(graph),
                "cycles": graph.cycles,
            }

        except Exception as e:
            logger.error(f"Failed to analyze project '{project_name}': {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def bulk_analyze(self) -> Dict[str, Any]:
        """Analyze all registered projects.

        Returns:
            Dictionary with results for each project
        """
        try:
            projects = self.registry.list()
            results = {}
            success_count = 0
            
            for project in projects:
                res = self.analyze_project(project.name)
                results[project.name] = res
                if res.get("success"):
                    success_count += 1
            
            return {
                "success": True,
                "total_projects": len(projects),
                "analyzed_successfully": success_count,
                "results": results
            }
        except Exception as e:
            logger.error(f"Failed in bulk analysis: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def merge_projects(self, project_names: List[str], new_project_name: str = "Merged_Project") -> Dict[str, Any]:
        """Merge multiple analyzed projects into a single graph.

        Args:
            project_names: List of project names to merge
            new_project_name: Name for the resulting merged project

        Returns:
            Result with merged graph statistics
        """
        try:
            # Validate input
            request = MergeProjectsRequest(project_names=project_names, new_project_name=new_project_name)
            
            if not request.project_names:
                return self._error_response(4003, "MERGE_ERROR", "No projects specified for merge")
            
            from karate_graph_analyzer.graph.core.graph_merger import DependencyGraphMerger
            merger = DependencyGraphMerger()
            merged_graph = None
            
            for name in request.project_names:
                if name not in self.graphs:
                    # Try to analyze it first if registered
                    project = self.registry.get(name)
                    if project:
                        self.analyze_project(name)
                    else:
                        logger.warning(f"Project '{name}' not found for merge, skipping")
                        continue
                
                graph = self.graphs[name]
                if merged_graph is None:
                    # Create the base graph for merging
                    merged_graph = DependencyGraph(
                        project_name=request.new_project_name,
                        nodes=graph.nodes.copy(),
                        edges=graph.edges.copy(),
                        cycles=graph.cycles.copy()
                    )
                else:
                    merged_graph = merger.merge(merged_graph, graph)
            
            if not merged_graph:
                return self._error_response(4003, "MERGE_ERROR", "No valid projects found to merge")
            
            self._store_runtime_graph(request.new_project_name, merged_graph)

            return {
                "success": True,
                "merged_project_name": request.new_project_name,
                "statistics": {
                    "total_nodes": len(merged_graph.nodes),
                    "total_edges": len(merged_graph.edges),
                    "projects_merged": request.project_names
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to merge projects: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def query_dependencies(
        self, component_id: str, transitive: bool = True
    ) -> Dict[str, Any]:
        """Query dependencies for a component.

        Args:
            component_id: Component identifier
            transitive: Include transitive dependencies
        """
        try:
            # Validate input
            request = QueryDependenciesRequest(component_id=component_id, transitive=transitive)

            # Find which project contains this component
            analyzer = self._find_analyzer_for_node(request.component_id)
            if not analyzer:
                return self._error_response(
                    4001, "QUERY_ERROR", f"Node '{component_id}' not found in any project"
                )

            # Query dependencies
            dependencies = analyzer.find_dependencies(request.component_id, transitive=transitive)

            # Convert to dictionaries
            result_nodes = [self._serialize_node_summary(node) for node in dependencies]

            logger.info(
                f"Found {len(result_nodes)} dependencies for component '{component_id}' "
                f"(transitive={transitive})"
            )

            return {
                "success": True,
                "component_id": component_id,
                "transitive": transitive,
                "dependencies": result_nodes,
                "count": len(result_nodes),
            }

        except Exception as e:
            logger.error(f"Failed to query dependencies for '{component_id}': {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def impact_analysis(self, component_id: str) -> Dict[str, Any]:
        """Perform impact analysis for component change.

        Args:
            component_id: Component identifier
        """
        try:
            # Validate input
            request = ImpactAnalysisRequest(component_id=component_id)

            # Find which project contains this component
            analyzer = self._find_analyzer_for_node(request.component_id)
            if not analyzer:
                return self._error_response(
                    4001, "QUERY_ERROR", f"Node '{component_id}' not found in any project"
                )

            # Perform impact analysis
            result = analyzer.impact_analysis(request.component_id)

            # Convert to dictionary
            affected_test_cases = []
            for test_case in result.affected_test_cases:
                # Get full node metadata to find the file path
                node = analyzer.graph.nodes.get(test_case.node_id)
                file_path = node.metadata.file_path if node else None
                
                affected_test_cases.append(
                    {
                        "node_id": test_case.node_id,
                        "name": test_case.name,
                        "jira_tags": test_case.jira_tags,
                        "dependency_path": test_case.dependency_path,
                        "depth": test_case.depth,
                        "line_number": test_case.line_number,
                        "source_snippet": get_source_snippet(file_path, test_case.line_number)
                    }
                )

            logger.info(
                f"Impact analysis for '{component_id}': {result.total_count} affected test cases"
            )

            return {
                "success": True,
                "changed_component": result.changed_component,
                "affected_test_cases": affected_test_cases,
                "total_count": result.total_count,
            }

        except Exception as e:
            logger.error(f"Failed to perform impact analysis for '{component_id}': {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def get_node_details(self, node_id: str) -> Dict[str, Any]:
        """Get full metadata for a node.

        Args:
            node_id: Node identifier
        """
        try:
            # Validate input
            request = GetNodeDetailsRequest(node_id=node_id)

            # Find which project contains this node
            for project_name, graph in self.graphs.items():
                if request.node_id in graph.nodes:
                    node = graph.nodes[request.node_id]

                    logger.info(f"Retrieved details for node '{node_id}'")

                    return {
                        "success": True,
                        "node": self._serialize_node_summary(
                            node,
                            include_additional_data=True,
                            include_source_snippet=True,
                        ),
                        "project_name": project_name,
                    }

            # Node not found
            return self._error_response(
                4001, "QUERY_ERROR", f"Node '{node_id}' not found in any project"
            )

        except Exception as e:
            logger.error(f"Failed to get node details for '{node_id}': {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def find_common_components(self, project_names: List[str]) -> Dict[str, Any]:
        """Find reusable components across projects.

        Args:
            project_names: List of project names to analyze
        """
        try:
            # Validate input
            request = FindCommonComponentsRequest(project_names=project_names)

            # Get projects from registry
            projects = []
            for project_name in request.project_names:
                project = self.registry.get(project_name)
                if not project:
                    return self._error_response(
                        3003,
                        "PROJECT_MANAGEMENT",
                        f"Project '{project_name}' not found in registry",
                    )
                projects.append(project)

            # Use any analyzer to find common components
            if not self.analyzers:
                return self._error_response(
                    4002,
                    "QUERY_ERROR",
                    "No projects have been analyzed. Analyze projects first.",
                )

            # Get first analyzer
            analyzer = next(iter(self.analyzers.values()))

            # Find common components
            common_components = analyzer.find_common_components(projects)

            # Convert to dictionaries
            result_components = []
            for component in common_components:
                instances = []
                for instance in component.instances:
                    instances.append(
                        {
                            "project_name": instance.project_name,
                            "file_path": instance.file_path,
                            "node_id": instance.node_id,
                        }
                    )

                result_components.append(
                    {
                        "type": component.type.value,
                        "name": component.name,
                        "usage_count": component.usage_count,
                        "instances": instances,
                    }
                )

            logger.info(
                f"Found {len(result_components)} common components across "
                f"{len(project_names)} projects"
            )

            return {
                "success": True,
                "project_names": project_names,
                "common_components": result_components,
                "count": len(result_components),
            }

        except Exception as e:
            logger.error(f"Failed to find common components: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def export_graph(self, project_name: str, format: str) -> Dict[str, Any]:
        """Export graph to JSON or GraphML.

        Args:
            project_name: Project name
            format: Export format ('json' or 'graphml')
        """
        try:
            # Validate input
            request = ExportGraphRequest(project_name=project_name, format=format)

            # Get graph
            if request.project_name not in self.graphs:
                return self._error_response(
                    3003,
                    "PROJECT_MANAGEMENT",
                    f"Project '{project_name}' has not been analyzed",
                )

            graph = self.graphs[request.project_name]

            # Use ExporterFactory
            try:
                exporter = ExporterFactory.create(request.format)
                export_data = exporter.export(graph)
            except ValueError as e:
                return self._error_response(
                    5001, "EXPORT_ERROR", str(e)
                )

            logger.info(f"Exported graph for project '{project_name}' to {format}")

            return {
                "success": True,
                "project_name": project_name,
                "format": request.format,
                "data": export_data,
            }

        except Exception as e:
            logger.error(f"Failed to export graph for '{project_name}': {e}")
            return self._error_response(5004, "EXPORT_ERROR", str(e))

    def render_execution_report(self, project_name: str, report_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate an execution report visualization (Living Graph)."""
        try:
            # Validate input
            request = RenderExecutionReportRequest(
                project_name=project_name, 
                report_path=report_path, 
                output_path=output_path
            )

            graph_error = self._require_graph(
                request.project_name,
                "Project '{project_name}' not found or not analyzed",
            )
            if graph_error:
                return graph_error

            analyzer_error = self._require_analyzer(request.project_name)
            if analyzer_error:
                return analyzer_error

            analyzer = self.analyzers[request.project_name]

            report_data = self._load_json_file(request.report_path)

            analyzer.apply_execution_report(
                report_data,
                run_context=self._build_report_run_context(request.report_path),
            )

            self._save_graph_state(project_name, analyzer.graph)

            return self.visualize_project(project_name, request.output_path)
            
        except Exception as e:
            logger.error(f"Failed to render execution report: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def compare_projects(self, base_project_name: str, new_project_name: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Compare two projects and generate a diff visualization report."""
        try:
            # Validate input
            request = CompareProjectsRequest(
                base_project_name=base_project_name,
                new_project_name=new_project_name,
                output_path=output_path
            )
            
            base_error = self._require_graph(
                request.base_project_name,
                "Base project '{project_name}' not found or not analyzed",
            )
            if base_error:
                return base_error

            new_error = self._require_graph(
                request.new_project_name,
                "New project '{project_name}' not found or not analyzed",
            )
            if new_error:
                return new_error

            base_graph = self.graphs[request.base_project_name]
            new_graph = self.graphs[request.new_project_name]
            output_path = request.output_path or self._resolve_timestamped_output_path(
                "diff_report",
                request.base_project_name,
                "vs",
                request.new_project_name,
            )
            final_path = self.report_service.render_diff(
                base_graph, new_graph, output_path
            )
            
            logger.info(f"Generated diff report for '{base_project_name}' vs '{new_project_name}' at {final_path}")
            
            return {
                "success": True,
                "message": "Project comparison report generated successfully",
                "output_path": final_path
            }
            
        except Exception as e:
            logger.error(f"Failed to compare projects: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def import_graph(self, data: str, format: str, project_name: str) -> Dict[str, Any]:
        """Import graph from JSON or GraphML."""
        try:
            # Validate input
            request = ImportGraphRequest(data=data, format=format, project_name=project_name)

            # Use ExporterFactory
            try:
                exporter = ExporterFactory.create(request.format)
                graph = exporter.import_graph(request.data, request.project_name)
            except json.JSONDecodeError as e:
                return self._error_response(
                    5001, "IMPORT_ERROR", f"Invalid JSON: {e}"
                )
            except ValueError as e:
                return self._error_response(
                    5002, "IMPORT_ERROR", str(e)
                )

            self._store_runtime_graph(request.project_name, graph)

            logger.info(
                f"Imported graph for project '{project_name}' from {format}: "
                f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
            )

            return {
                "success": True,
                "project_name": request.project_name,
                "format": request.format,
                "statistics": self._build_graph_statistics(graph),
            }

        except Exception as e:
            logger.error(f"Failed to import graph: {e}")
            return self._error_response(5003, "IMPORT_ERROR", str(e))

    def _find_analyzer_for_node(self, node_id: str) -> Optional[DependencyAnalyzer]:
        """Find the analyzer that contains the specified node."""
        return self.runtime_store.find_analyzer_for_node(node_id)

    # Legacy export/import methods
    def _export_to_json(self, graph: DependencyGraph) -> str:
        from karate_graph_analyzer.exporters.json_exporter import JsonExporter
        return JsonExporter().export(graph)

    def _export_to_graphml(self, graph: DependencyGraph) -> str:
        from karate_graph_analyzer.exporters.graphml_exporter import GraphMLExporter
        return GraphMLExporter().export(graph)

    def _import_from_json(self, data: str, project_name: str) -> DependencyGraph:
        from karate_graph_analyzer.exporters.json_exporter import JsonExporter
        return JsonExporter().import_graph(data, project_name)

    def _import_from_graphml(self, data: str, project_name: str) -> DependencyGraph:
        from karate_graph_analyzer.exporters.graphml_exporter import GraphMLExporter
        return GraphMLExporter().import_graph(data, project_name)
    
    # ========== Search and Query Methods ==========
    
    def search_api(
        self,
        project_name: str,
        method: Optional[str] = None,
        path: Optional[str] = None,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.search_api(project_name, method, path, domain)
        )
    
    def get_api_stats(self, project_name: str, keyword: Optional[str] = None) -> Dict[str, Any]:
        def _action(query_api: Any) -> Dict[str, Any]:
            stats = query_api.get_api_stats(keyword)
            return {
                "success": True,
                "project_name": project_name,
                "keyword_filter": keyword,
                "total_apis": stats["total_count"],
                "domain_breakdown": stats["domain_breakdown"],
                "apis": stats["results"],
            }

        return self._with_query_api(project_name, _action)
    
    def get_page_stats(self, project_name: str, domain: Optional[str] = None) -> Dict[str, Any]:
        def _action(query_api: Any) -> Dict[str, Any]:
            stats = query_api.get_page_stats(domain)
            return {
                "success": True,
                "project_name": project_name,
                "domain_filter": domain,
                "total_pages": stats["total_count"],
                "domain_breakdown": stats["domain_breakdown"],
                "pages": stats["results"],
            }

        return self._with_query_api(project_name, _action)
    
    def search_workflow(self, project_name: str, path: Optional[str] = None, scenario_tag: Optional[str] = None, keyword: Optional[str] = None) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.search_workflow(project_name, path, scenario_tag, keyword)
        )
    
    def search_page(self, project_name: str, path: Optional[str] = None, action_tag: Optional[str] = None) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.search_page(project_name, path, action_tag)
        )
    
    def search_test_case(self, project_name: str, jira_tag: Optional[str] = None, name_pattern: Optional[str] = None, uses_api: Optional[str] = None, uses_workflow: Optional[str] = None) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.search_test_case(
                project_name, jira_tag, name_pattern, uses_api, uses_workflow
            )
        )

    def search_java_usage(
        self,
        project_name: str,
        query: str,
        include_methods: bool = True,
    ) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.search_java_usage(project_name, query, include_methods)
        )

    def search_js_usage(
        self,
        project_name: str,
        query: str = "",
        include_functions: bool = True,
    ) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.search_js_usage(project_name, query, include_functions)
        )

    def search_error_pattern(
        self,
        project_name: str,
        pattern: str,
        limit: int = 50,
    ) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.search_error_pattern(project_name, pattern, limit)
        )

    def search_reusable_function(
        self,
        project_name: str,
        query: str,
        language: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        graph_error = self._require_graph(project_name)
        if graph_error:
            return graph_error

        project = self.registry.get(project_name)
        project_root = project.root_path if project else None
        graph = self.graphs[project_name]
        service = ReusableFunctionSearchService()

        def _action(query_api: Any) -> Dict[str, Any]:
            return service.search(project_root, graph, query_api, query, language, limit)

        return self._with_query_api(project_name, _action)
    
    def get_usage_stats(self, project_name: str, node_id: str) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.get_usage_stats(project_name, node_id)
        )
    
    def get_most_used_components(self, project_name: str, component_type: str, limit: int = 10) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.get_most_used_components(project_name, component_type, limit)
        )
    
    def find_unused_components(self, project_name: str) -> Dict[str, Any]:
        return self._with_search_tools(
            lambda tools: tools.find_unused_components(project_name)
        )

    def top_hotspots(self, project_name: str, limit: int = 10) -> Dict[str, Any]:
        """Preset: return top failure hotspots."""
        request = QueryPresetRequest(project_name=project_name, limit=limit)
        hotspots_result = self.get_failure_hotspots(request.project_name)
        if not hotspots_result.get("success"):
            return hotspots_result

        hotspots = hotspots_result.get("hotspots", [])
        return {
            "success": True,
            "preset": "top-hotspots",
            "project_name": request.project_name,
            "limit": request.limit,
            "results": hotspots[: request.limit],
            "count": min(len(hotspots), request.limit),
            "total_available": len(hotspots),
        }

    def unused_components(self, project_name: str, limit: int = 10) -> Dict[str, Any]:
        """Preset: return flattened unused component list."""
        request = QueryPresetRequest(project_name=project_name, limit=limit)
        unused_result = self.find_unused_components(request.project_name)
        if not unused_result.get("success"):
            return unused_result

        flattened: List[Dict[str, Any]] = []
        by_type = unused_result.get("unused_components", {})
        for component_type, nodes in by_type.items():
            for node in nodes:
                item = dict(node)
                item["component_type"] = component_type
                flattened.append(item)

        flattened.sort(key=lambda item: item.get("name", ""))
        return {
            "success": True,
            "preset": "unused-components",
            "project_name": request.project_name,
            "limit": request.limit,
            "results": flattened[: request.limit],
            "count": min(len(flattened), request.limit),
            "total_available": len(flattened),
        }

    def flaky_risk(self, project_name: str, limit: int = 10) -> Dict[str, Any]:
        """Preset: return test cases with mixed pass/fail history."""
        request = QueryPresetRequest(project_name=project_name, limit=limit)
        graph_error = self._require_graph(request.project_name)
        if graph_error:
            return graph_error

        graph = self.graphs[request.project_name]
        flaky_items: List[Dict[str, Any]] = []

        for node in graph.nodes.values():
            if node.type.value != "TEST_CASE":
                continue

            history = node.metadata.execution_history or []
            if len(history) < 2:
                continue

            pass_count = sum(1 for status in history if status == "PASSED")
            fail_count = sum(1 for status in history if status == "FAILED")
            if pass_count == 0 or fail_count == 0:
                continue

            total_runs = pass_count + fail_count
            failure_rate = fail_count / total_runs if total_runs else 0.0
            flaky_score = min(pass_count, fail_count) / total_runs if total_runs else 0.0

            flaky_items.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "jira_tags": node.metadata.jira_tags,
                    "total_runs": total_runs,
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                    "failure_rate": round(failure_rate, 4),
                    "flaky_score": round(flaky_score, 4),
                    "last_status": node.execution_status,
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                }
            )

        flaky_items.sort(
            key=lambda item: (item["flaky_score"], item["total_runs"], item["failure_rate"]),
            reverse=True,
        )

        return {
            "success": True,
            "preset": "flaky-risk",
            "project_name": request.project_name,
            "limit": request.limit,
            "results": flaky_items[: request.limit],
            "count": min(len(flaky_items), request.limit),
            "total_available": len(flaky_items),
        }

    def _match_changed_nodes(
        self,
        graph: DependencyGraph,
        changed_paths: List[str],
    ) -> List[Any]:
        """Resolve changed path patterns to graph nodes."""
        patterns = [p.strip().replace("\\", "/").lower() for p in changed_paths if p and p.strip()]
        if not patterns:
            return []

        matched = []
        seen: Set[str] = set()
        for node in graph.nodes.values():
            file_path = (node.metadata.file_path or "").replace("\\", "/").lower()
            name = (node.name or "").replace("\\", "/").lower()
            haystacks = [file_path, name]
            if any(pattern in h for pattern in patterns for h in haystacks if h):
                if node.id not in seen:
                    matched.append(node)
                    seen.add(node.id)
        return matched

    def change_impact_preview(
        self,
        project_name: str,
        changed_paths: List[str],
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Preview impacted test cases from changed files/components."""
        try:
            request = ChangeImpactPreviewRequest(
                project_name=project_name,
                changed_paths=changed_paths,
                limit=limit,
            )

            graph_error = self._require_graph(request.project_name)
            if graph_error:
                return graph_error

            analyzer_error = self._require_analyzer(request.project_name)
            if analyzer_error:
                return analyzer_error

            graph = self.graphs[request.project_name]
            analyzer = self.analyzers[request.project_name]
            matched_nodes = self._match_changed_nodes(graph, request.changed_paths)

            impacted_map: Dict[str, Dict[str, Any]] = {}
            for changed in matched_nodes:
                impact = analyzer.impact_analysis(changed.id)
                for affected in impact.affected_test_cases:
                    existing = impacted_map.get(affected.node_id)
                    candidate = {
                        "node_id": affected.node_id,
                        "name": affected.name,
                        "jira_tags": affected.jira_tags,
                        "min_depth": affected.depth,
                        "change_triggers": [changed.name],
                        "paths": [affected.dependency_path],
                    }
                    if not existing:
                        impacted_map[affected.node_id] = candidate
                        continue
                    existing["min_depth"] = min(existing.get("min_depth", affected.depth), affected.depth)
                    if changed.name not in existing["change_triggers"]:
                        existing["change_triggers"].append(changed.name)
                    if affected.dependency_path not in existing["paths"]:
                        existing["paths"].append(affected.dependency_path)

            impacted = list(impacted_map.values())
            impacted.sort(
                key=lambda item: (
                    -len(item.get("change_triggers", [])),
                    item.get("min_depth", 9999),
                    item.get("name", ""),
                )
            )

            return {
                "success": True,
                "preset": "change-impact-preview",
                "project_name": request.project_name,
                "changed_paths": request.changed_paths,
                "matched_changed_nodes": [
                    {
                        "id": node.id,
                        "type": node.type.value,
                        "name": node.name,
                        "file_path": node.metadata.file_path,
                    }
                    for node in matched_nodes
                ],
                "impacted_test_cases": impacted[: request.limit],
                "count": min(len(impacted), request.limit),
                "total_available": len(impacted),
            }

        except Exception as e:
            logger.error(f"Failed to build change impact preview: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def test_selection_suggestion(
        self,
        project_name: str,
        changed_paths: List[str],
        limit: int = 30,
    ) -> Dict[str, Any]:
        """Suggest minimal high-signal tests to rerun after changes."""
        try:
            request = TestSelectionSuggestionRequest(
                project_name=project_name,
                changed_paths=changed_paths,
                limit=limit,
            )

            preview = self.change_impact_preview(
                request.project_name,
                request.changed_paths,
                limit=500,
            )
            if not preview.get("success"):
                return preview

            impacted = preview.get("impacted_test_cases", [])
            selected = []
            for item in impacted:
                priority_score = (len(item.get("change_triggers", [])) * 10) - item.get("min_depth", 0)
                selected.append(
                    {
                        "node_id": item.get("node_id"),
                        "name": item.get("name"),
                        "jira_tags": item.get("jira_tags", []),
                        "priority_score": priority_score,
                        "reason": f"triggered_by={len(item.get('change_triggers', []))}, min_depth={item.get('min_depth')}",
                        "change_triggers": item.get("change_triggers", []),
                    }
                )

            selected.sort(
                key=lambda x: (
                    x.get("priority_score", 0),
                    len(x.get("change_triggers", [])),
                    x.get("name", ""),
                ),
                reverse=True,
            )

            return {
                "success": True,
                "preset": "test-selection-suggestion",
                "project_name": request.project_name,
                "changed_paths": request.changed_paths,
                "selection_strategy": "priority = trigger_count*10 - min_depth",
                "suggested_tests": selected[: request.limit],
                "count": min(len(selected), request.limit),
                "total_available": len(selected),
            }

        except Exception as e:
            logger.error(f"Failed to suggest test selection: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

<<<<<<< Updated upstream
=======
    def feature_intent_index(
        self,
        project_name: str,
        query: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Index scenario intent summaries so AI can search feature behavior."""
        try:
            request = FeatureIntentIndexRequest(
                project_name=project_name,
                query=query,
                limit=limit,
            )
            service, error = self._feature_understanding_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "feature-intent-index",
                "project_name": request.project_name,
                "query": request.query,
                **service.feature_intent_index(request.query, request.limit),
            }
        except Exception as e:
            logger.error(f"Failed to build feature intent index: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def variable_data_flow_trace(
        self,
        project_name: str,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Trace feature variables from definition/source to usage points."""
        try:
            request = FeatureScenarioSelectorRequest(
                project_name=project_name,
                feature_path=feature_path,
                scenario_tag=scenario_tag,
                scenario_name=scenario_name,
                node_id=node_id,
                limit=limit,
            )
            service, error = self._feature_understanding_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "variable-data-flow-trace",
                "project_name": request.project_name,
                **service.variable_data_flow_trace(
                    request.feature_path,
                    request.scenario_tag,
                    request.scenario_name,
                    request.node_id,
                    request.limit,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to build variable data flow trace: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def assertion_map(
        self,
        project_name: str,
        query: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Index status/match/assert steps across feature files."""
        try:
            request = AssertionMapRequest(project_name=project_name, query=query, limit=limit)
            service, error = self._feature_understanding_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "assertion-map",
                "project_name": request.project_name,
                "query": request.query,
                **service.assertion_map(request.query, request.limit),
            }
        except Exception as e:
            logger.error(f"Failed to build assertion map: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def call_read_deep_context(
        self,
        project_name: str,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        max_depth: int = 2,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Return nested call/read context for selected scenarios."""
        try:
            request = CallReadDeepContextRequest(
                project_name=project_name,
                feature_path=feature_path,
                scenario_tag=scenario_tag,
                scenario_name=scenario_name,
                node_id=node_id,
                max_depth=max_depth,
                limit=limit,
            )
            service, error = self._feature_understanding_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "call-read-deep-context",
                "project_name": request.project_name,
                **service.call_read_deep_context(
                    request.feature_path,
                    request.scenario_tag,
                    request.scenario_name,
                    request.node_id,
                    request.max_depth,
                    request.limit,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to build call/read deep context: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def ai_feature_context_pack(
        self,
        project_name: str,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        max_call_depth: int = 2,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Build an AI-ready feature pack: intent, variables, assertions, calls, graph context."""
        try:
            request = AiFeatureContextPackRequest(
                project_name=project_name,
                feature_path=feature_path,
                scenario_tag=scenario_tag,
                scenario_name=scenario_name,
                node_id=node_id,
                max_call_depth=max_call_depth,
                limit=limit,
            )
            service, error = self._feature_understanding_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "ai-feature-context-pack",
                "project_name": request.project_name,
                **service.ai_feature_context_pack(
                    request.feature_path,
                    request.scenario_tag,
                    request.scenario_name,
                    request.node_id,
                    request.max_call_depth,
                    request.limit,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to build AI feature context pack: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def feature_behavior_map(
        self,
        project_name: str,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Build scenario behavior map: preconditions, actions, expectations."""
        try:
            request = FeatureScenarioSelectorRequest(
                project_name=project_name,
                feature_path=feature_path,
                scenario_tag=scenario_tag,
                scenario_name=scenario_name,
                node_id=node_id,
                limit=limit,
            )
            service, error = self._feature_understanding_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "feature-behavior-map",
                "project_name": request.project_name,
                **service.feature_behavior_map(
                    request.feature_path,
                    request.scenario_tag,
                    request.scenario_name,
                    request.node_id,
                    request.limit,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to build feature behavior map: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def scenario_similarity_map(
        self,
        project_name: str,
        query: Optional[str] = None,
        limit: int = 50,
        top_k: int = 3,
    ) -> Dict[str, Any]:
        """Build scenario similarity map from intent keywords."""
        try:
            request = ScenarioSimilarityMapRequest(
                project_name=project_name,
                query=query,
                limit=limit,
                top_k=top_k,
            )
            service, error = self._feature_understanding_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "scenario-similarity-map",
                "project_name": request.project_name,
                "query": request.query,
                **service.scenario_similarity_map(
                    request.query,
                    request.limit,
                    request.top_k,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to build scenario similarity map: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def feature_reuse_advisor(
        self,
        project_name: str,
        min_group_size: int = 2,
        min_flow_length: int = 3,
        limit: int = 50,
        include_low_signal: bool = False,
    ) -> Dict[str, Any]:
        """Find duplicate feature steps/flows and return AI-safe refactor suggestions."""
        try:
            request = FeatureReuseAdvisorRequest(
                project_name=project_name,
                min_group_size=min_group_size,
                min_flow_length=min_flow_length,
                limit=limit,
                include_low_signal=include_low_signal,
            )
            service, error = self._feature_understanding_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "feature-reuse-advisor",
                "project_name": request.project_name,
                **service.feature_reuse_advisor(
                    request.min_group_size,
                    request.min_flow_length,
                    request.limit,
                    request.include_low_signal,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to build feature reuse advisor: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def db_query_index(
        self,
        project_name: str,
        query: Optional[str] = None,
        limit: int = 100,
        include_components: bool = True,
    ) -> Dict[str, Any]:
        """Build/search DB query and DB component index."""
        try:
            request = DbQueryIndexRequest(
                project_name=project_name,
                query=query,
                limit=limit,
                include_components=include_components,
            )
            service, error = self._db_tracking_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "db-query-index",
                "project_name": request.project_name,
                "query": request.query,
                **service.db_query_index(
                    request.query,
                    request.limit,
                    request.include_components,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to build DB query index: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def search_db_usage(
        self,
        project_name: str,
        query: str,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Search DB usage by table/query/operation/host/path keywords."""
        try:
            request = DbSearchUsageRequest(
                project_name=project_name,
                query=query,
                limit=limit,
            )
            service, error = self._db_tracking_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "search-db-usage",
                "project_name": request.project_name,
                "query": request.query,
                **service.search_db_usage(request.query, request.limit),
            }
        except Exception as e:
            logger.error(f"Failed to search DB usage: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def db_data_flow_trace(
        self,
        project_name: str,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Trace DB-related variables/calls/assertions in selected scenarios."""
        try:
            request = DbScenarioTraceRequest(
                project_name=project_name,
                feature_path=feature_path,
                scenario_tag=scenario_tag,
                scenario_name=scenario_name,
                node_id=node_id,
                limit=limit,
            )
            service, error = self._db_tracking_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "db-data-flow-trace",
                "project_name": request.project_name,
                **service.db_data_flow_trace(
                    request.feature_path,
                    request.scenario_tag,
                    request.scenario_name,
                    request.node_id,
                    request.limit,
                ),
            }
        except Exception as e:
            logger.error(f"Failed to build DB data flow trace: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def db_assertion_map(
        self,
        project_name: str,
        query: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Index DB-related assertions across feature files."""
        try:
            request = DbQueryIndexRequest(
                project_name=project_name,
                query=query,
                limit=limit,
                include_components=True,
            )
            service, error = self._db_tracking_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "db-assertion-map",
                "project_name": request.project_name,
                "query": request.query,
                **service.db_assertion_map(request.query, request.limit),
            }
        except Exception as e:
            logger.error(f"Failed to build DB assertion map: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def db_impact_preview(
        self,
        project_name: str,
        changed_entities: List[str],
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Preview impacted tests from changed DB entities."""
        try:
            request = DbImpactPreviewRequest(
                project_name=project_name,
                changed_entities=changed_entities,
                limit=limit,
            )
            service, error = self._db_tracking_service(request.project_name)
            if error:
                return error
            return {
                "success": True,
                "preset": "db-impact-preview",
                "project_name": request.project_name,
                "changed_entities": request.changed_entities,
                **service.db_impact_preview(request.changed_entities, request.limit),
            }
        except Exception as e:
            logger.error(f"Failed to build DB impact preview: {e}", exc_info=True)
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

>>>>>>> Stashed changes
    def prioritize_fix_queue(self, project_name: str, limit: int = 10) -> Dict[str, Any]:
        """Preset: rank components to fix first by impact + risk."""
        request = QueryPresetRequest(project_name=project_name, limit=limit)

        hotspots_result = self.get_failure_hotspots(request.project_name)
        if not hotspots_result.get("success"):
            return hotspots_result

        graph_error = self._require_graph(request.project_name)
        if graph_error:
            return graph_error

        graph = self.graphs[request.project_name]
        analyzer = self.analyzers.get(request.project_name)

        impacted_by_node: Dict[str, Dict[str, Any]] = {}
        for hotspot in hotspots_result.get("hotspots", []):
            hotspot_node_id = hotspot.get("node_id")
            if hotspot_node_id:
                impacted_by_node[hotspot_node_id] = {
                    "score": hotspot.get("failure_impact_score", 0),
                    "failure_rate": hotspot.get("failure_percentage", 0),
                    "hotspot_name": hotspot.get("name"),
                    "hotspot_type": hotspot.get("type"),
                }
            for tc in hotspot.get("affected_failed_test_cases", []):
                tc_id = tc.get("node_id") or tc.get("id")
                if not tc_id:
                    continue
                existing = impacted_by_node.get(tc_id)
                candidate = {
                    "score": hotspot.get("failure_impact_score", 0),
                    "failure_rate": hotspot.get("failure_percentage", 0),
                    "hotspot_name": hotspot.get("name"),
                    "hotspot_type": hotspot.get("type"),
                }
                if not existing or candidate["score"] > existing["score"]:
                    impacted_by_node[tc_id] = candidate

        ranked: List[Dict[str, Any]] = []
        for node_id, hotspot_info in impacted_by_node.items():
            node = graph.nodes.get(node_id)
            if not node:
                continue

            history = self.failure_context_service.build_history_payload(node)
            fail_count = history.get("fail_count", 0)
            total_runs = history.get("total_runs", 0)
            failure_rate = history.get("failure_rate", 0.0)
            flaky_score = history.get("flaky_score", 0.0)
            impact_score = hotspot_info.get("score", 0)

            # Weighted score favoring blast radius first, then severity, then instability.
            priority_score = (
                (impact_score * 10.0)
                + (failure_rate * 100.0)
                + (flaky_score * 20.0)
            )

            reason_parts = []
            reason_parts.append(f"impact={impact_score}")
            reason_parts.append(f"failure_rate={round(failure_rate * 100, 1)}%")
            if total_runs > 1:
                reason_parts.append(f"runs={total_runs}")
            if flaky_score > 0:
                reason_parts.append(f"flaky={round(flaky_score, 3)}")

            top_fp = (history.get("failure_fingerprints") or [])
            top_fingerprint = top_fp[0]["fingerprint"] if top_fp else None

            ranked.append(
                {
                    "node_id": node.id,
                    "name": node.name,
                    "type": node.type.value,
                    "status": node.execution_status,
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                    "priority_score": round(priority_score, 3),
                    "impact_score": impact_score,
                    "failure_rate": failure_rate,
                    "fail_count": fail_count,
                    "total_runs": total_runs,
                    "flaky_score": flaky_score,
                    "failure_category": node.metadata.additional_data.get("failure_category"),
                    "top_fingerprint": top_fingerprint,
                    "linked_hotspot": {
                        "name": hotspot_info.get("hotspot_name"),
                        "type": hotspot_info.get("hotspot_type"),
                        "failure_rate": hotspot_info.get("failure_rate"),
                    },
                    "why_now": ", ".join(reason_parts),
                }
            )

        ranked.sort(
            key=lambda item: (
                item["priority_score"],
                item["impact_score"],
                item["failure_rate"],
                item["fail_count"],
            ),
            reverse=True,
        )

        return {
            "success": True,
            "preset": "prioritize-fix-queue",
            "project_name": request.project_name,
            "limit": request.limit,
            "results": ranked[: request.limit],
            "count": min(len(ranked), request.limit),
            "total_available": len(ranked),
            "scoring": {
                "formula": "priority = impact*10 + failure_rate*100 + flaky_score*20",
                "weights": {"impact": 10, "failure_rate": 100, "flaky_score": 20},
            },
        }

    def get_project_health(self, project_name: str) -> Dict[str, Any]:
        analyzer_error = self._require_analyzer(project_name)
        if analyzer_error:
            return analyzer_error
        analyzer = self.analyzers[project_name]
        summary = analyzer.expert.get_health_summary()
        return {
            "success": True,
            "project_name": project_name,
            "health": summary
        }

    def find_redundant_components(self, project_name: str) -> Dict[str, Any]:
        analyzer_error = self._require_analyzer(project_name)
        if analyzer_error:
            return analyzer_error
        analyzer = self.analyzers[project_name]
        duplicates = analyzer.expert.find_redundant_apis()
        results = {}
        for key, nodes in duplicates.items():
            results[key] = [{"id": n.id, "name": n.name, "file_path": n.metadata.file_path, "line_number": n.metadata.line_number} for n in nodes]
        return {"success": True, "project_name": project_name, "redundant_apis": results, "count": len(results)}

    def common_usage_map(self, project_name: str, limit: int = 50) -> Dict[str, Any]:
        """Return reusable components sorted by how many test cases use them."""
        request = QueryPresetRequest(project_name=project_name, limit=limit)
        graph_error = self._require_graph(request.project_name)
        if graph_error:
            return graph_error

        from karate_graph_analyzer.graph.graph_query import GraphQuery

        graph = self.graphs[request.project_name]
        query = GraphQuery(graph)
        reusable_types = {
            NodeType.COMMON,
            NodeType.SCENARIO,
            NodeType.WORKFLOW,
            NodeType.PAGE,
            NodeType.ACTION,
            NodeType.API,
            NodeType.DATA,
            NodeType.DATABASE,
            NodeType.JAVASCRIPT,
            NodeType.JS_FUNCTION,
        }

        results: List[Dict[str, Any]] = []
        for node in graph.nodes.values():
            if node.type not in reusable_types:
                continue

            stats = query.get_usage_stats(node)
            usage_count = stats.get("usage_count", 0)
            if usage_count == 0:
                continue

            results.append(
                {
                    "id": node.id,
                    "type": node.type.value,
                    "name": node.name,
                    "usage_count": usage_count,
                    "used_by_test_cases": stats.get("used_by_test_cases", []),
                    "direct_dependencies": stats.get("direct_dependencies", []),
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                    "scenario_tag": node.metadata.additional_data.get("scenario_tag"),
                    "action_tag": node.metadata.additional_data.get("action_tag"),
                }
            )

        results.sort(
            key=lambda item: (
                item["usage_count"],
                item["type"] in {"COMMON", "SCENARIO", "WORKFLOW", "PAGE", "ACTION"},
                item["name"],
            ),
            reverse=True,
        )

        return {
            "success": True,
            "preset": "common-usage-map",
            "project_name": request.project_name,
            "limit": request.limit,
            "results": results[: request.limit],
            "count": min(len(results), request.limit),
            "total_available": len(results),
        }

    def javascript_structure_map(self, project_name: str, limit: int = 100) -> Dict[str, Any]:
        """Return JavaScript files, exported functions, dependencies, and test usage."""
        request = QueryPresetRequest(project_name=project_name, limit=limit)
        graph_error = self._require_graph(request.project_name)
        if graph_error:
            return graph_error

        from karate_graph_analyzer.graph.graph_query import GraphQuery

        graph = self.graphs[request.project_name]
        query = GraphQuery(graph)
        results: List[Dict[str, Any]] = []

        for node in graph.nodes.values():
            if node.type != NodeType.JAVASCRIPT:
                continue

            stats = query.get_usage_stats(node)
            functions = []
            dependencies = []
            for edge in graph.edges.values():
                if edge.from_node != node.id:
                    continue
                target = graph.nodes.get(edge.to_node)
                if not target:
                    continue
                item = {
                    "id": target.id,
                    "type": target.type.value,
                    "name": target.name,
                    "file_path": target.metadata.file_path,
                    "line_number": target.metadata.line_number,
                }
                if target.type == NodeType.JS_FUNCTION:
                    item["function_kind"] = target.metadata.additional_data.get("function_kind")
                    item["usage_count"] = query.get_usage_stats(target).get("usage_count", 0)
                    functions.append(item)
                else:
                    item["dependency_type"] = edge.type.value
                    dependencies.append(item)

            results.append(
                {
                    "id": node.id,
                    "type": node.type.value,
                    "name": node.name,
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                    "default_function_node_id": node.metadata.additional_data.get("default_function_node_id"),
                    "usage_count": stats.get("usage_count", 0),
                    "used_by_test_cases": stats.get("used_by_test_cases", []),
                    "functions": sorted(functions, key=lambda item: (item.get("line_number") or 0, item["name"])),
                    "dependencies": sorted(dependencies, key=lambda item: (item["type"], item["name"])),
                }
            )

        results.sort(key=lambda item: (item["usage_count"], item["name"]), reverse=True)
        return {
            "success": True,
            "preset": "javascript-structure-map",
            "project_name": request.project_name,
            "limit": request.limit,
            "results": results[: request.limit],
            "count": min(len(results), request.limit),
            "total_available": len(results),
        }

    def similar_common_components(self, project_name: str, limit: int = 50) -> Dict[str, Any]:
        """Find reusable scenario/common/action nodes with the same dependency shape."""
        request = QueryPresetRequest(project_name=project_name, limit=limit)
        graph_error = self._require_graph(request.project_name)
        if graph_error:
            return graph_error

        graph = self.graphs[request.project_name]
        comparable_types = {NodeType.COMMON, NodeType.SCENARIO, NodeType.WORKFLOW, NodeType.ACTION}
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for node in graph.nodes.values():
            if node.type not in comparable_types:
                continue

            deps = []
            for edge in graph.edges.values():
                if edge.from_node != node.id:
                    continue
                target = graph.nodes.get(edge.to_node)
                if not target:
                    continue
                deps.append(f"{target.type.value}:{target.name}")

            if not deps:
                continue

            signature = "|".join(sorted(set(deps)))
            groups.setdefault(signature, []).append(
                {
                    "id": node.id,
                    "type": node.type.value,
                    "name": node.name,
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                    "scenario_tag": node.metadata.additional_data.get("scenario_tag"),
                    "action_tag": node.metadata.additional_data.get("action_tag"),
                    "dependencies": sorted(set(deps)),
                }
            )

        duplicate_groups = [
            {
                "signature": signature,
                "component_count": len(nodes),
                "components": nodes,
            }
            for signature, nodes in groups.items()
            if len(nodes) > 1
        ]
        duplicate_groups.sort(key=lambda item: item["component_count"], reverse=True)

        return {
            "success": True,
            "preset": "similar-common-components",
            "project_name": request.project_name,
            "limit": request.limit,
            "results": duplicate_groups[: request.limit],
            "count": min(len(duplicate_groups), request.limit),
            "total_available": len(duplicate_groups),
        }

    def get_failure_hotspots(self, project_name: str) -> Dict[str, Any]:
        analyzer_error = self._require_analyzer(project_name)
        if analyzer_error:
            return analyzer_error
        analyzer = self.analyzers[project_name]
        hotspots = analyzer.find_failure_hotspots()
        return {"success": True, "project_name": project_name, "hotspots": hotspots, "count": len(hotspots)}

    def record_fix(self, project_name: str, node_id: str, error_message: str, solution: str, description: str) -> Dict[str, Any]:
        analyzer_error = self._require_analyzer(project_name)
        if analyzer_error:
            return analyzer_error
        analyzer = self.analyzers[project_name]
        node = analyzer.graph.nodes.get(node_id)
        name = node.name if node else node_id
        file_path = node.metadata.file_path if node else None
        analyzer.fix_expert.record_fix(node_id, name, error_message, solution, description, file_path)
        return {"success": True, "message": f"Recorded fix for {name}"}

    def get_fix_suggestions(self, project_name: str, node_id: str, error_message: str) -> Dict[str, Any]:
        analyzer_error = self._require_analyzer(project_name)
        if analyzer_error:
            return analyzer_error
        analyzer = self.analyzers[project_name]
        
        # 1. Get historical fixes
        historical_suggestions = analyzer.fix_expert.suggest_fixes(node_id, error_message)
        
        # 2. Get smart AI suggestion (live analysis)
        # We need the project root path
        project_root = ""
        for p in self.registry.list():
            if p.name == project_name:
                project_root = p.root_path
                break
                
        smart_suggestion = analyzer.get_smart_fix_suggestion(node_id, error_message, project_root)
        
        return {
            "success": True, 
            "project_name": project_name, 
            "node_id": node_id, 
            "smart_suggestion": smart_suggestion,
            "historical_suggestions": historical_suggestions, 
            "count": len(historical_suggestions) + (1 if smart_suggestion else 0)
        }

    def auto_fix_hint_pack(
        self,
        project_name: str,
        node_id: str,
        error_message: str,
        max_historical: int = 3,
    ) -> Dict[str, Any]:
        """Build a step-by-step checklist from smart and historical suggestions."""
        request = AutoFixHintPackRequest(
            project_name=project_name,
            node_id=node_id,
            error_message=error_message,
            max_historical=max_historical,
        )

        suggestions_result = self.get_fix_suggestions(
            request.project_name, request.node_id, request.error_message
        )
        if not suggestions_result.get("success"):
            return suggestions_result

        checklist: List[Dict[str, Any]] = []

        smart = suggestions_result.get("smart_suggestion") or {}
        if isinstance(smart, dict) and smart and not smart.get("error"):
            checklist.append(
                {
                    "step": 1,
                    "source": "smart",
                    "title": f"Validate root cause: {smart.get('root_cause', 'Unknown')}",
                    "action": smart.get("suggestion", "Inspect the failing component logic."),
                    "confidence": smart.get("confidence", 0.0),
                    "details": {
                        "node_name": smart.get("node_name"),
                        "node_type": smart.get("node_type"),
                        "error_summary": smart.get("error_summary"),
                        "file_path": smart.get("file_path"),
                    },
                }
            )

        historical_suggestions = suggestions_result.get("historical_suggestions", [])
        for index, item in enumerate(historical_suggestions[: request.max_historical], start=1):
            checklist.append(
                {
                    "step": len(checklist) + 1,
                    "source": "historical",
                    "title": f"Apply historical fix pattern #{index}",
                    "action": item.get("description", "Reuse previous successful remediation."),
                    "confidence": item.get("confidence", 0.0),
                    "details": {
                        "solution": item.get("solution"),
                        "error_pattern": item.get("error_pattern"),
                        "times_used": item.get("success_count", item.get("times_used")),
                        "last_used": item.get("timestamp", item.get("last_used")),
                    },
                }
            )

        checklist.append(
            {
                "step": len(checklist) + 1,
                "source": "workflow",
                "title": "Re-run impacted scope",
                "action": "Execute impacted tests first, then full regression for this project.",
                "confidence": 1.0,
                "details": {
                    "project_name": request.project_name,
                    "node_id": request.node_id,
                },
            }
        )

        return {
            "success": True,
            "preset": "auto-fix-hint-pack",
            "project_name": request.project_name,
            "node_id": request.node_id,
            "error_message": request.error_message,
            "checklist": checklist,
            "count": len(checklist),
            "smart_suggestion_available": bool(smart and not smart.get("error")),
            "historical_suggestions_available": len(historical_suggestions),
        }

    def get_failure_history(self, project_name: str, node_id: str) -> Dict[str, Any]:
        """Return execution history and fingerprint trend for one node."""
        try:
            request = FailureHistoryRequest(project_name=project_name, node_id=node_id)
            graph_error = self._require_graph(request.project_name)
            if graph_error:
                return graph_error

            graph = self.graphs[request.project_name]
            node = graph.nodes.get(request.node_id)
            if not node:
                return self._error_response(
                    4001, "QUERY_ERROR", f"Node '{request.node_id}' not found"
                )

            return {
                "success": True,
                "project_name": request.project_name,
                "node_id": request.node_id,
                "node": self.failure_context_service.build_node_payload(node),
                "failure": self.failure_context_service.build_failure_payload(node),
                "history": self.failure_context_service.build_history_payload(node),
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def get_failure_debug_context(
        self,
        project_name: str,
        node_id: str,
        error_message: Optional[str] = None,
        radius: int = 2,
        max_historical: int = 3,
    ) -> Dict[str, Any]:
        """Build an AI-ready context pack for debugging one failure."""
        try:
            request = FailureDebugContextRequest(
                project_name=project_name,
                node_id=node_id,
                error_message=error_message,
                radius=radius,
                max_historical=max_historical,
            )

            graph_error = self._require_graph(request.project_name)
            if graph_error:
                return graph_error
            analyzer_error = self._require_analyzer(request.project_name)
            if analyzer_error:
                return analyzer_error

            graph = self.graphs[request.project_name]
            analyzer = self.analyzers[request.project_name]
            if request.node_id not in graph.nodes:
                return self._error_response(
                    4001, "QUERY_ERROR", f"Node '{request.node_id}' not found"
                )

            context = self.failure_context_service.build_debug_context(
                graph,
                analyzer,
                request.node_id,
                request.error_message,
                request.radius,
            )

            resolved_error = context["failure"].get("error_message") or request.error_message or ""
            fix_guidance = (
                self.auto_fix_hint_pack(
                    request.project_name,
                    request.node_id,
                    resolved_error,
                    request.max_historical,
                )
                if resolved_error
                else {
                    "success": True,
                    "preset": "auto-fix-hint-pack",
                    "checklist": [],
                    "count": 0,
                    "message": "No error message available for fix hint generation.",
                }
            )

            return {
                "success": True,
                "tool": "get_failure_debug_context",
                "project_name": request.project_name,
                "node_id": request.node_id,
                **context,
                "fix_guidance": fix_guidance,
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def get_subgraph(self, node_id: str, radius: int = 2) -> Dict[str, Any]:
        try:
            request = GetSubgraphRequest(node_id=node_id, radius=radius)
            analyzer = self._find_analyzer_for_node(request.node_id)
            if not analyzer:
                return self._error_response(4001, "QUERY_ERROR", f"Node '{node_id}' not found")
            return {
                "success": True,
                "node_id": node_id,
                "radius": radius,
                "subgraph": analyzer.get_subgraph(request.node_id, radius=request.radius),
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def query_node_by_metadata(self, key: str, value: str) -> Dict[str, Any]:
        try:
            request = QueryNodeByMetadataRequest(key=key, value=value)
            all_results = self._collect_cross_project_search_results(
                lambda analyzer: analyzer.query_by_metadata(request.key, request.value)
            )
            return {
                "success": True,
                "key": key,
                "value": value,
                "results": all_results,
                "count": len(all_results),
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def global_search(self, query: str) -> Dict[str, Any]:
        try:
            request = GlobalSearchRequest(query=query)
            all_results = self._collect_cross_project_search_results(
                lambda analyzer: analyzer.global_search(request.query)
            )
            return {
                "success": True,
                "query": query,
                "results": all_results,
                "count": len(all_results),
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def find_path(self, source_id: str, target_id: str) -> Dict[str, Any]:
        try:
            request = FindPathRequest(source_id=source_id, target_id=target_id)
            analyzer = self._find_analyzer_for_node(source_id)
            if not analyzer:
                return self._error_response(4001, "QUERY_ERROR", f"Source node '{source_id}' not found")
            paths = analyzer.find_paths(request.source_id, request.target_id)
            return {
                "success": True,
                "source_id": source_id,
                "target_id": target_id,
                "paths": paths,
                "count": len(paths),
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def get_component_importance(self, project_name: str) -> Dict[str, Any]:
        try:
            analyzer_error = self._require_analyzer(project_name)
            if analyzer_error:
                return analyzer_error
            analyzer = self.analyzers[project_name]
            importance = analyzer.get_component_importance()
            return {
                "success": True,
                "project_name": project_name,
                "importance": importance[:20],
                "total_count": len(importance),
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def get_impact_radius(self, node_id: str, depth: int = 2) -> Dict[str, Any]:
        try:
            analyzer = self._find_analyzer_for_node(node_id)
            if not analyzer:
                return self._error_response(4001, "QUERY_ERROR", f"Node '{node_id}' not found")
            neighborhood_ids = nx.single_source_shortest_path_length(
                analyzer._nx_graph.reverse(), node_id, cutoff=depth
            )
            impacted_nodes = []
            for nid, dist in neighborhood_ids.items():
                if nid == node_id:
                    continue
                node = analyzer.graph.nodes[nid]
                node_item = self._serialize_node_summary(node, include_metadata=False)
                node_item["distance"] = dist
                node_item["category"] = (
                    node.metadata.category.value if node.metadata.category else "UNKNOWN"
                )
                impacted_nodes.append(node_item)
            return {
                "success": True,
                "node_id": node_id,
                "radius": depth,
                "impacted_count": len(impacted_nodes),
                "impacted_nodes": impacted_nodes,
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def visualize_project(self, project_name: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        graph_error = self._require_graph(project_name)
        if graph_error:
            return graph_error
        graph = self.graphs[project_name]
        output_path = self._resolve_project_visualization_path(project_name, output_path)
        try:
            mode = VisualizationMode.DEFAULT
            if any(node.execution_status for node in graph.nodes.values()):
                mode = VisualizationMode.EXECUTION
            final_path = self._render_graph_visualization(graph, mode, output_path)
            return {
                "success": True,
                "project_name": project_name,
                "visualization_path": final_path,
                "message": f"Visualization generated successfully at {final_path}",
            }
        except Exception as e:
            return self._error_response(8001, "VISUALIZATION_ERROR", str(e))

    def process_reports_folder(self, project_name: str, directory_path: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        try:
            analyzer_error = self._require_analyzer(project_name)
            if analyzer_error:
                return analyzer_error
            analyzer = self.analyzers[project_name]
            ai_summary = analyzer.process_execution_directory(directory_path)
            self._save_graph_state(project_name, analyzer.graph)
            viz_result = self.visualize_project(project_name, output_path)
            return {
                "success": True,
                "project_name": project_name,
                "ai_summary": ai_summary,
                "visualization_path": viz_result.get("visualization_path"),
                "message": "Processed directory successfully.",
            }
        except Exception as e:
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def _save_graph_state(self, project_name: str, graph: DependencyGraph) -> bool:
        project = self.registry.get(project_name)
        if project:
            return self.graph_cache.save_project_graph(
                project,
                graph,
                getattr(graph, "include_structural_nodes", False),
            )
        return self.graph_cache.save_raw_graph(project_name, graph)

    def _load_graph_state(self, project_name: str) -> Optional[DependencyGraph]:
        project = self.registry.get(project_name)
        if project:
            return self.graph_cache.load_if_fresh(
                project,
                include_structural_nodes=False,
            )
        return None

    def _error_response(self, code: Any, category: str, message: str) -> Dict[str, Any]:
        return error_response(code=code, category=category, message=message)
