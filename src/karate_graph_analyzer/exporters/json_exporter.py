"""
JSON graph exporter.

Strategy Pattern implementation for exporting/importing DependencyGraph as JSON.
"""

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict

from karate_graph_analyzer.interfaces import IGraphExporter
from karate_graph_analyzer.models import (
    ComponentCategory,
    DependencyGraph,
    DependencyType,
    DiffStatus,
    Edge,
    FlowType,
    Node,
    NodeMetadata,
    NodeType,
    ParserConfig,
)


class JsonExporter(IGraphExporter):
    """Exports and imports DependencyGraph in JSON format."""

    def export(self, graph: DependencyGraph) -> str:
        """Export graph to JSON format.

        Args:
            graph: Dependency graph to export

        Returns:
            JSON string representation
        """
        # Convert graph to dictionary
        nodes_list = []
        for node in graph.nodes.values():
            nodes_list.append(
                {
                    "id": node.id,
                    "type": node.type.value,
                    "name": node.name,
                    "tags": node.tags,
                    "execution_status": node.execution_status,
                    "execution_details": node.execution_details,
                    "diff_status": node.diff_status.value,
                    "metadata": {
                        "file_path": node.metadata.file_path,
                        "line_number": node.metadata.line_number,
                        "jira_tags": node.metadata.jira_tags,
                        "project_name": node.metadata.project_name,
                        "category": node.metadata.category.value if hasattr(node.metadata.category, 'value') else node.metadata.category,
                        "flow": node.metadata.flow.value if hasattr(node.metadata.flow, 'value') else node.metadata.flow,
                        "additional_data": node.metadata.additional_data,
                        "environment_variants": getattr(node.metadata, "environment_variants", {}),
                        "execution_history": getattr(node.metadata, "execution_history", []),
                        "expert_notes": getattr(node.metadata, "expert_notes", []),
                        "suggestions": getattr(node.metadata, "suggestions", []),
                    },
                }
            )

        edges_list = []
        for edge in graph.edges.values():
            edges_list.append(
                {
                    "id": edge.id,
                    "from_node": edge.from_node,
                    "to_node": edge.to_node,
                    "type": edge.type.value,
                    "line_number": edge.line_number,
                    "diff_status": edge.diff_status.value,
                }
            )

        export_data = {
            "project_name": graph.project_name,
            "timestamp": datetime.now().isoformat(),
            "nodes": nodes_list,
            "edges": edges_list,
            "cycles": graph.cycles,
            "config": asdict(graph.config) if graph.config else None,
            "include_structural_nodes": getattr(graph, "include_structural_nodes", False),
        }

        return json.dumps(export_data, ensure_ascii=False, separators=(",", ":"))

    def import_graph(self, data: str, project_name: str) -> DependencyGraph:
        """Import graph from JSON format.

        Args:
            data: JSON string
            project_name: Project name for imported graph

        Returns:
            Reconstructed dependency graph

        Raises:
            ValueError: If data structure is invalid
            json.JSONDecodeError: If JSON is malformed
        """
        # Parse JSON
        graph_data = json.loads(data)

        # Validate structure
        if "nodes" not in graph_data or "edges" not in graph_data:
            raise ValueError("Invalid graph data: missing 'nodes' or 'edges'")

        # Reconstruct nodes
        nodes: Dict[str, Node] = {}
        for node_data in graph_data["nodes"]:
            metadata = NodeMetadata(
                file_path=node_data["metadata"].get("file_path"),
                line_number=node_data["metadata"].get("line_number"),
                jira_tags=node_data["metadata"].get("jira_tags", []),
                project_name=node_data["metadata"].get("project_name", project_name),
                category=ComponentCategory(node_data["metadata"].get("category", "UNKNOWN")),
                flow=FlowType(node_data["metadata"].get("flow", "UNKNOWN")),
                additional_data=node_data["metadata"].get("additional_data", {}),
                environment_variants=node_data["metadata"].get("environment_variants", {}),
                execution_history=node_data["metadata"].get("execution_history", []),
                expert_notes=node_data["metadata"].get("expert_notes", []),
                suggestions=node_data["metadata"].get("suggestions", []),
            )

            node = Node(
                id=node_data["id"],
                type=NodeType(node_data["type"]),
                name=node_data["name"],
                metadata=metadata,
                tags=node_data.get("tags", []),
                execution_status=node_data.get("execution_status"),
                execution_details=node_data.get("execution_details", {}),
                diff_status=DiffStatus(node_data.get("diff_status", "UNCHANGED")),
            )
            nodes[node.id] = node

        # Reconstruct edges
        edges: Dict[str, Edge] = {}
        for edge_data in graph_data["edges"]:
            # Validate edge references existing nodes
            if edge_data["from_node"] not in nodes:
                raise ValueError(
                    f"Edge references non-existent node: {edge_data['from_node']}"
                )
            if edge_data["to_node"] not in nodes:
                raise ValueError(
                    f"Edge references non-existent node: {edge_data['to_node']}"
                )

            edge = Edge(
                id=edge_data["id"],
                from_node=edge_data["from_node"],
                to_node=edge_data["to_node"],
                type=DependencyType(edge_data["type"]),
                line_number=edge_data.get("line_number"),
                diff_status=DiffStatus(edge_data.get("diff_status", "UNCHANGED")),
            )
            edges[edge.id] = edge

        # Reconstruct cycles
        cycles = graph_data.get("cycles", [])
        config_data = graph_data.get("config")
        config = ParserConfig(**config_data) if config_data else None

        return DependencyGraph(
            project_name=project_name, 
            nodes=nodes, 
            edges=edges, 
            cycles=cycles, 
            config=config,
            include_structural_nodes=graph_data.get("include_structural_nodes", False)
        )
