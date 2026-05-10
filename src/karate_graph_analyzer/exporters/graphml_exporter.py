"""
GraphML graph exporter.

Strategy Pattern implementation for exporting/importing DependencyGraph as GraphML.
"""

from io import BytesIO, StringIO
from typing import Dict

import networkx as nx

from karate_graph_analyzer.interfaces import IGraphExporter
from karate_graph_analyzer.models import (
    DependencyGraph,
    DependencyType,
    Edge,
    Node,
    NodeMetadata,
    NodeType,
)


class GraphMLExporter(IGraphExporter):
    """Exports and imports DependencyGraph in GraphML format."""

    def export(self, graph: DependencyGraph) -> str:
        """Export graph to GraphML format.

        Args:
            graph: Dependency graph to export

        Returns:
            GraphML string representation
        """
        # Create NetworkX graph
        nx_graph = nx.DiGraph()

        # Add nodes with attributes
        for node in graph.nodes.values():
            nx_graph.add_node(
                node.id,
                type=node.type.value,
                name=node.name,
                file_path=node.metadata.file_path or "",
                line_number=str(node.metadata.line_number or 0),
                jira_tags=",".join(node.metadata.jira_tags),
                project_name=node.metadata.project_name,
            )

        # Add edges with attributes
        for edge in graph.edges.values():
            nx_graph.add_edge(edge.from_node, edge.to_node, type=edge.type.value)

        # Convert to GraphML using BytesIO and decode to string
        output = BytesIO()
        nx.write_graphml(nx_graph, output)
        return output.getvalue().decode("utf-8")

    def import_graph(self, data: str, project_name: str) -> DependencyGraph:
        """Import graph from GraphML format.

        Args:
            data: GraphML string
            project_name: Project name for imported graph

        Returns:
            Reconstructed dependency graph
        """
        # Parse GraphML
        input_stream = StringIO(data)
        nx_graph = nx.read_graphml(input_stream)

        # Reconstruct nodes
        nodes: Dict[str, Node] = {}
        for node_id in nx_graph.nodes():
            node_data = nx_graph.nodes[node_id]

            # Parse jira_tags from comma-separated string
            jira_tags_str = node_data.get("jira_tags", "")
            jira_tags = [tag.strip() for tag in jira_tags_str.split(",") if tag.strip()]

            metadata = NodeMetadata(
                file_path=node_data.get("file_path") or None,
                line_number=int(node_data.get("line_number", 0)) or None,
                jira_tags=jira_tags,
                project_name=node_data.get("project_name", project_name),
                additional_data={},
            )

            node = Node(
                id=node_id,
                type=NodeType(node_data.get("type", "TEST_CASE")),
                name=node_data.get("name", node_id),
                metadata=metadata,
            )
            nodes[node.id] = node

        # Reconstruct edges
        edges: Dict[str, Edge] = {}
        for from_node, to_node in nx_graph.edges():
            edge_data = nx_graph.edges[from_node, to_node]
            edge_id = f"edge_{from_node}_{to_node}"

            edge = Edge(
                id=edge_id,
                from_node=from_node,
                to_node=to_node,
                type=DependencyType(edge_data.get("type", "WORKFLOW")),
            )
            edges[edge.id] = edge

        # Detect cycles (GraphML doesn't store cycles). Full cycle enumeration
        # can be very expensive for large imported graphs, so cap it.
        if nx_graph.number_of_nodes() > 20000:
            cycles = []
        else:
            try:
                cycles = list(nx.simple_cycles(nx_graph))
            except Exception:
                cycles = []

        return DependencyGraph(
            project_name=project_name, nodes=nodes, edges=edges, cycles=cycles
        )
