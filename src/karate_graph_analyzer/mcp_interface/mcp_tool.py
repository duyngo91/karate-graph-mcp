"""
MCP tool interface implementation.

Provides MCP protocol interface for graph analyzer.
"""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
from karate_graph_analyzer.cache.cache_manager import CacheManager
from karate_graph_analyzer.exporters import ExporterFactory
from karate_graph_analyzer.graph.graph_builder import GraphBuilder
from karate_graph_analyzer.mcp_interface.search_tools import SearchTools
from karate_graph_analyzer.models import (
    DependencyGraph,
    ImpactResult,
    ParserConfig,
    Project,
    ReusableComponent,
    VisualizationMode,
)
from karate_graph_analyzer.visualization.graph_visualizer import GraphVisualizer
from karate_graph_analyzer.parser.execution_parser import ExecutionReportParser
from karate_graph_analyzer.analyzer.graph_diff import GraphComparator
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


class KarateGraphAnalyzerTool:
    """MCP protocol interface for graph analyzer."""

    def __init__(self, storage_path: str = ".karate_projects.json") -> None:
        """Initialize MCP tool interface.

        Args:
            storage_path: Path to project registry storage file
        """
        self.registry = ProjectRegistry(storage_path=storage_path)
        self.cache_manager = CacheManager()
        self.graphs: Dict[str, DependencyGraph] = {}  # project_name -> graph
        self.analyzers: Dict[str, DependencyAnalyzer] = {}  # project_name -> analyzer
        self.search_tools: Optional[SearchTools] = None  # Initialized after first graph is loaded

        # Load existing projects from storage
        try:
            self.registry.load()
            logger.info(f"Loaded {len(self.registry.list())} projects from registry")
        except Exception as e:
            logger.warning(f"Failed to load project registry: {e}")

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

            # Remove from in-memory graphs and analyzers
            if request.project_name in self.graphs:
                del self.graphs[request.project_name]
            if request.project_name in self.analyzers:
                del self.analyzers[request.project_name]

            # Update search tools
            if self.search_tools:
                self.search_tools.graphs = self.graphs
                self.search_tools.query_apis.clear()

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

            # Clear memory
            self.graphs.clear()
            self.analyzers.clear()

            # Update search tools
            if self.search_tools:
                self.search_tools.graphs = self.graphs
                self.search_tools.query_apis.clear()

            logger.info(f"Cleared all {count} projects")

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

    def analyze_project(self, project_name: str) -> Dict[str, Any]:
        """Build dependency graph for project."""
        print(f"DEBUG: Analyzing project {project_name} - VERSION V11-CLEAN-2")
        try:
            # Validate input
            request = AnalyzeProjectRequest(project_name=project_name)

            # Get project from registry
            project = self.registry.get(request.project_name)
            if not project:
                return self._error_response(
                    3003,
                    "PROJECT_MANAGEMENT",
                    f"Project '{project_name}' not found in registry",
                )

            # Build graph
            builder = GraphBuilder()
            graph = builder.build_from_project(project)

            # Store graph and create analyzer
            self.graphs[project_name] = graph
            self.analyzers[project_name] = DependencyAnalyzer(graph)
            
            # Initialize or update search tools
            if self.search_tools is None:
                self.search_tools = SearchTools(self.graphs)
            else:
                # Update search tools with new graph
                self.search_tools.graphs = self.graphs
                self.search_tools.query_apis.clear()  # Clear cache to rebuild with new graphs

            # Calculate statistics
            node_counts = {}
            for node in graph.nodes.values():
                node_type = node.type.value
                node_counts[node_type] = node_counts.get(node_type, 0) + 1

            logger.info(
                f"Analyzed project '{project_name}': "
                f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
            )

            return {
                "success": True,
                "project_name": project_name,
                "message": f"Analysis completed for {project_name} [VERSION V12-ENV-FIX]",
                "statistics": {
                    "total_nodes": len(graph.nodes),
                    "total_edges": len(graph.edges),
                    "node_counts": node_counts,
                    "cycles_detected": len(graph.cycles),
                },
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
            
            # Store merged graph
            self.graphs[request.new_project_name] = merged_graph
            self.analyzers[request.new_project_name] = DependencyAnalyzer(merged_graph)
            
            # Update search tools
            if self.search_tools:
                self.search_tools.graphs = self.graphs
                self.search_tools.query_apis.clear()

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

        Returns:
            Dependency result dictionary
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
            result_nodes = []
            for node in dependencies:
                result_nodes.append(
                    {
                        "id": node.id,
                        "type": node.type.value,
                        "name": node.name,
                        "metadata": {
                            "file_path": node.metadata.file_path,
                            "line_number": node.metadata.line_number,
                            "jira_tags": node.metadata.jira_tags,
                            "project_name": node.metadata.project_name,
                        },
                    }
                )

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

        Returns:
            Impact analysis result dictionary
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

        Returns:
            Node details dictionary
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
                        "node": {
                            "id": node.id,
                            "type": node.type.value,
                            "name": node.name,
                            "metadata": {
                                "file_path": node.metadata.file_path,
                                "line_number": node.metadata.line_number,
                                "jira_tags": node.metadata.jira_tags,
                                "project_name": node.metadata.project_name,
                                "source_snippet": get_source_snippet(node.metadata.file_path, node.metadata.line_number),
                                "additional_data": node.metadata.additional_data,
                            },
                        },
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

        Returns:
            Dictionary with list of reusable components
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

            # Get first analyzer (method is static-like, doesn't depend on specific graph)
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

        Returns:
            Dictionary with exported graph data
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

            # Use ExporterFactory (Strategy + Factory Pattern)
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
        """Generate an execution report visualization (Living Graph).
        
        Args:
            project_name: Name of the analyzed project
            report_path: Path to the Karate execution report (JSON)
            output_path: Optional custom output path
        """
        try:
            # Validate input
            request = RenderExecutionReportRequest(
                project_name=project_name, 
                report_path=report_path, 
                output_path=output_path
            )

            if request.project_name not in self.graphs:
                return self._error_response(3003, "PROJECT_MANAGEMENT", f"Project '{project_name}' not found or not analyzed")

            graph = self.graphs[request.project_name]
            
            # 1. Parse report and apply to graph
            parser = ExecutionReportParser(graph)
            applied_count = parser.apply_reports([request.report_path])
            
            # 2. Render in EXECUTION mode
            if not request.output_path:
                # Default output path
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                request.output_path = str(Path("output") / f"execution_report_{request.project_name}_{timestamp}.html")
            
            visualizer = GraphVisualizer(graph, mode=VisualizationMode.EXECUTION)
            visualizer.render(request.output_path)
            
            logger.info(f"Generated execution report for '{project_name}' at {request.output_path}")
            
            return {
                "success": True,
                "message": f"Execution report generated successfully ({applied_count} results applied)",
                "output_path": request.output_path,
                "applied_results": applied_count
            }
            
        except Exception as e:
            logger.error(f"Failed to render execution report: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def compare_projects(self, base_project_name: str, new_project_name: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Compare two projects and generate a diff visualization report.
        
        Args:
            base_project_name: Name of the base project
            new_project_name: Name of the new project
            output_path: Optional custom output path
        """
        try:
            # Validate input
            request = CompareProjectsRequest(
                base_project_name=base_project_name,
                new_project_name=new_project_name,
                output_path=output_path
            )
            
            if request.base_project_name not in self.graphs:
                return self._error_response(3003, "PROJECT_MANAGEMENT", f"Base project '{base_project_name}' not found or not analyzed")
            
            if request.new_project_name not in self.graphs:
                return self._error_response(3003, "PROJECT_MANAGEMENT", f"New project '{new_project_name}' not found or not analyzed")
            
            base_graph = self.graphs[request.base_project_name]
            new_graph = self.graphs[request.new_project_name]
            
            # 1. Compare graphs
            comparator = GraphComparator()
            diff_graph = comparator.compare(base_graph, new_graph)
            
            # 2. Render in DIFF mode
            if not request.output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                request.output_path = str(Path("output") / f"diff_report_{request.base_project_name}_vs_{request.new_project_name}_{timestamp}.html")
                
            visualizer = GraphVisualizer(diff_graph, mode=VisualizationMode.DIFF)
            visualizer.render(request.output_path)
            
            logger.info(f"Generated diff report for '{base_project_name}' vs '{new_project_name}' at {request.output_path}")
            
            return {
                "success": True,
                "message": "Project comparison report generated successfully",
                "output_path": request.output_path
            }
            
        except Exception as e:
            logger.error(f"Failed to compare projects: {e}")
            return self._error_response(6003, "INTERNAL_ERROR", str(e))

    def import_graph(self, data: str, format: str, project_name: str) -> Dict[str, Any]:
        """Import graph from JSON or GraphML.

        Args:
            data: Graph data string
            format: Import format ('json' or 'graphml')
            project_name: Project name for imported graph

        Returns:
            Result dictionary with success status
        """
        try:
            # Validate input
            request = ImportGraphRequest(data=data, format=format, project_name=project_name)

            # Use ExporterFactory (Strategy + Factory Pattern)
            try:
                exporter = ExporterFactory.create(request.format)
                graph = exporter.import_graph(request.data, request.project_name)
            except json.JSONDecodeError as e:
                # json.JSONDecodeError is a subclass of ValueError — catch first
                return self._error_response(
                    5001, "IMPORT_ERROR", f"Invalid JSON: {e}"
                )
            except ValueError as e:
                return self._error_response(
                    5002, "IMPORT_ERROR", str(e)
                )

            # Store graph and create analyzer
            self.graphs[request.project_name] = graph
            self.analyzers[request.project_name] = DependencyAnalyzer(graph)

            logger.info(
                f"Imported graph for project '{project_name}' from {format}: "
                f"{len(graph.nodes)} nodes, {len(graph.edges)} edges"
            )

            return {
                "success": True,
                "project_name": request.project_name,
                "format": request.format,
                "statistics": {
                    "total_nodes": len(graph.nodes),
                    "total_edges": len(graph.edges),
                    "cycles_detected": len(graph.cycles),
                },
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to import graph: invalid JSON - {e}")
            return self._error_response(5001, "IMPORT_ERROR", f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to import graph: {e}")
            return self._error_response(5003, "IMPORT_ERROR", str(e))

    def _find_analyzer_for_node(self, node_id: str) -> Optional[DependencyAnalyzer]:
        """Find the analyzer that contains the specified node.

        Args:
            node_id: Node identifier

        Returns:
            DependencyAnalyzer if found, None otherwise
        """
        for project_name, graph in self.graphs.items():
            if node_id in graph.nodes:
                return self.analyzers.get(project_name)
        return None

    # Legacy export/import methods — delegate to ExporterFactory for backward compatibility

    def _export_to_json(self, graph: DependencyGraph) -> str:
        """Export graph to JSON format (delegates to JsonExporter)."""
        from karate_graph_analyzer.exporters.json_exporter import JsonExporter
        return JsonExporter().export(graph)

    def _export_to_graphml(self, graph: DependencyGraph) -> str:
        """Export graph to GraphML format (delegates to GraphMLExporter)."""
        from karate_graph_analyzer.exporters.graphml_exporter import GraphMLExporter
        return GraphMLExporter().export(graph)

    def _import_from_json(self, data: str, project_name: str) -> DependencyGraph:
        """Import graph from JSON format (delegates to JsonExporter)."""
        from karate_graph_analyzer.exporters.json_exporter import JsonExporter
        return JsonExporter().import_graph(data, project_name)

    def _import_from_graphml(self, data: str, project_name: str) -> DependencyGraph:
        """Import graph from GraphML format (delegates to GraphMLExporter)."""
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
        """Search for API endpoints.
        
        Args:
            project_name: Name of the project
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: API path pattern
            domain: Domain name
        
        Returns:
            Dictionary with search results
        """
        if self.search_tools is None:
            return self._error_response(
                7000,
                "SEARCH_ERROR",
                "No projects have been analyzed. Analyze a project first."
            )
        
        return self.search_tools.search_api(project_name, method, path, domain)
    
    def get_api_stats(self, project_name: str, keyword: Optional[str] = None) -> Dict[str, Any]:
        """Get API statistics for an analyzed project.
        
        Args:
            project_name: Name of the project
            keyword: Optional keyword to filter APIs (e.g. 't24')
            
        Returns:
            Dictionary with API counts and breakdown
        """
        query_api = self.search_tools._get_query_api(project_name)
        if not query_api:
             return self._error_response(3003, "PROJECT_MANAGEMENT", f"Project '{project_name}' not found")
             
        stats = query_api.get_api_stats(keyword)

        return {
            "success": True,
            "project_name": project_name,
            "keyword_filter": keyword,
            "total_apis": stats["total_count"],
            "domain_breakdown": stats["domain_breakdown"],
            "apis": stats["results"]
        }
    
    def get_page_stats(self, project_name: str, domain: Optional[str] = None) -> Dict[str, Any]:
        """Get Page statistics for an analyzed project.
        
        Args:
            project_name: Name of the project
            domain: Optional business domain to filter pages
            
        Returns:
            Dictionary with page counts and breakdown
        """
        query_api = self.search_tools._get_query_api(project_name)
        if not query_api:
             return self._error_response(3003, "PROJECT_MANAGEMENT", f"Project '{project_name}' not found")
             
        stats = query_api.get_page_stats(domain)

        return {
            "success": True,
            "project_name": project_name,
            "domain_filter": domain,
            "total_pages": stats["total_count"],
            "domain_breakdown": stats["domain_breakdown"],
            "pages": stats["results"]
        }
    
    def search_workflow(
        self,
        project_name: str,
        path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        keyword: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for workflows and scenarios.
        
        Args:
            project_name: Name of the project
            path: Workflow file path pattern
            scenario_tag: Scenario tag (e.g., '@AddPayment')
            keyword: Full-text search keyword
        
        Returns:
            Dictionary with search results
        """
        if self.search_tools is None:
            return self._error_response(
                7000,
                "SEARCH_ERROR",
                "No projects have been analyzed. Analyze a project first."
            )
        
        return self.search_tools.search_workflow(project_name, path, scenario_tag, keyword)
    
    def search_page(
        self,
        project_name: str,
        path: Optional[str] = None,
        action_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for pages and actions.
        
        Args:
            project_name: Name of the project
            path: Page file path pattern
            action_tag: Action tag (e.g., '@login')
        
        Returns:
            Dictionary with search results
        """
        if self.search_tools is None:
            return self._error_response(
                7000,
                "SEARCH_ERROR",
                "No projects have been analyzed. Analyze a project first."
            )
        
        return self.search_tools.search_page(project_name, path, action_tag)
    
    def search_test_case(
        self,
        project_name: str,
        jira_tag: Optional[str] = None,
        name_pattern: Optional[str] = None,
        uses_api: Optional[str] = None,
        uses_workflow: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for test cases.
        
        Args:
            project_name: Name of the project
            jira_tag: Jira tag (e.g., '@JiraId-123')
            name_pattern: Test case name pattern
            uses_api: API endpoint used by test
            uses_workflow: Workflow used by test
        
        Returns:
            Dictionary with search results
        """
        if self.search_tools is None:
            return self._error_response(
                7000,
                "SEARCH_ERROR",
                "No projects have been analyzed. Analyze a project first."
            )
        
        return self.search_tools.search_test_case(
            project_name, jira_tag, name_pattern, uses_api, uses_workflow
        )
    
    def get_usage_stats(
        self,
        project_name: str,
        node_id: str
    ) -> Dict[str, Any]:
        """Get usage statistics for a node.
        
        Args:
            project_name: Name of the project
            node_id: Node ID
        
        Returns:
            Dictionary with usage statistics
        """
        if self.search_tools is None:
            return self._error_response(
                7000,
                "SEARCH_ERROR",
                "No projects have been analyzed. Analyze a project first."
            )
        
        return self.search_tools.get_usage_stats(project_name, node_id)
    
    def get_most_used_components(
        self,
        project_name: str,
        component_type: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get most used components.
        
        Args:
            project_name: Name of the project
            component_type: Type of component ('api', 'workflow', 'page')
            limit: Maximum number of results
        
        Returns:
            Dictionary with most used components
        """
        if self.search_tools is None:
            return self._error_response(
                7000,
                "SEARCH_ERROR",
                "No projects have been analyzed. Analyze a project first."
            )
        
        return self.search_tools.get_most_used_components(project_name, component_type, limit)
    
    def find_unused_components(
        self,
        project_name: str
    ) -> Dict[str, Any]:
        """Find unused components.
        
        Args:
            project_name: Name of the project
        
        Returns:
            Dictionary with unused components by type
        """
        if self.search_tools is None:
            return self._error_response(
                7000,
                "SEARCH_ERROR",
                "No projects have been analyzed. Analyze a project first."
            )
        
        return self.search_tools.find_unused_components(project_name)

    def get_project_health(self, project_name: str) -> Dict[str, Any]:
        """Get architectural health report for a project.
        
        Args:
            project_name: Name of the project
            
        Returns:
            Health report dictionary
        """
        if project_name not in self.analyzers:
            return self._error_response(7001, "PROJECT_NOT_FOUND", f"Project '{project_name}' not found")
        
        analyzer = self.analyzers[project_name]
        summary = analyzer.expert.get_health_summary()
        
        return {
            "success": True,
            "project_name": project_name,
            "health": summary
        }

    def find_redundant_components(self, project_name: str) -> Dict[str, Any]:
        """Find potential duplicate API definitions.
        
        Args:
            project_name: Name of the project
            
        Returns:
            Dictionary of redundant components
        """
        if project_name not in self.analyzers:
            return self._error_response(7001, "PROJECT_NOT_FOUND", f"Project '{project_name}' not found")
        
        analyzer = self.analyzers[project_name]
        duplicates = analyzer.expert.find_redundant_apis()
        
        results = {}
        for key, nodes in duplicates.items():
            results[key] = [
                {
                    "id": node.id,
                    "name": node.name,
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number
                }
                for node in nodes
            ]
            
        return {
            "success": True,
            "project_name": project_name,
            "redundant_apis": results,
            "count": len(results)
        }

    def visualize_project(self, project_name: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Generate interactive HTML visualization for a project.
        
        Args:
            project_name: Name of the project
            output_path: Optional output path for HTML file
            
        Returns:
            Dictionary with visualization path
        """
        if project_name not in self.graphs:
            return self._error_response(3003, "PROJECT_MANAGEMENT", f"Project '{project_name}' has not been analyzed")
        
        graph = self.graphs[project_name]
        
        # Default output path
        if not output_path:
            # Try to save in project root / output
            project = self.registry.get(project_name)
            if project:
                out_dir = Path(project.root_path) / "output"
                out_dir.mkdir(exist_ok=True)
                output_path = str(out_dir / f"{project_name}_graph.html")
            else:
                output_path = f"{project_name}_graph.html"
        
        try:
            visualizer = GraphVisualizer(graph)
            final_path = visualizer.render(output_path=output_path)
            
            return {
                "success": True,
                "project_name": project_name,
                "visualization_path": final_path,
                "message": f"Visualization generated successfully at {final_path}"
            }
        except Exception as e:
            logger.error(f"Failed to visualize project '{project_name}': {e}")
            return self._error_response(8001, "VISUALIZATION_ERROR", str(e))

    def _error_response(self, code: Any, category: str, message: str) -> Dict[str, Any]:
        """Create structured error response.

        Args:
            code: Error code (integer)
            category: Error category
            message: Error message

        Returns:
            Error response dictionary
        """
        return {
            "success": False,
            "error": {
                "code": str(code),
                "category": category,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            },
        }
