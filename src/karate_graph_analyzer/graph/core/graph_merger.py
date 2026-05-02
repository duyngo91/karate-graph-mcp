"""
Logic for merging multiple dependency graphs.
"""

import re
from typing import Dict, List, Optional, Tuple
from karate_graph_analyzer.models import DependencyGraph, Node, Edge, NodeType

class DependencyGraphMerger:
    """Handles merging logic for DependencyGraph instances."""

    def merge(self, base_graph: DependencyGraph, other: DependencyGraph, new_project_name: Optional[str] = None) -> DependencyGraph:
        """Merge 'other' graph into 'base_graph' and return the result."""
        if new_project_name:
            base_graph.project_name = new_project_name

        node_id_map: Dict[str, str] = {}
        namespace = re.sub(r"[^A-Za-z0-9_]+", "_", other.project_name).strip("_") or "project"

        for node_id, node in other.nodes.items():
            target_id = node_id
            existing = base_graph.nodes.get(target_id)
            if existing and not self._same_node_identity(existing, node):
                target_id = f"{namespace}_{node_id}"
                node = Node(
                    id=target_id,
                    type=node.type,
                    name=node.name,
                    metadata=node.metadata,
                    tags=node.tags,
                    execution_status=node.execution_status,
                    execution_details=node.execution_details,
                    diff_status=node.diff_status
                )
            node_id_map[node_id] = target_id
            base_graph.nodes[target_id] = node

        for edge_id, edge in other.edges.items():
            from_node = node_id_map.get(edge.from_node, edge.from_node)
            to_node = node_id_map.get(edge.to_node, edge.to_node)
            target_edge_id = f"edge_{from_node}_{to_node}_{edge.type.value}_{edge.line_number or 0}"
            if target_edge_id in base_graph.edges:
                continue
            base_graph.edges[target_edge_id] = Edge(
                id=target_edge_id,
                from_node=from_node,
                to_node=to_node,
                type=edge.type,
                line_number=edge.line_number,
                diff_status=edge.diff_status
            )
        
        for cycle in other.cycles:
            if cycle not in base_graph.cycles:
                base_graph.cycles.append(cycle)
                
        return base_graph

    def _same_node_identity(self, left: Node, right: Node) -> bool:
        return (
            left.type == right.type
            and left.name == right.name
            and left.metadata.project_name == right.metadata.project_name
            and left.metadata.file_path == right.metadata.file_path
            and left.metadata.line_number == right.metadata.line_number
        )
