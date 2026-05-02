import logging
from typing import Dict, List, Tuple, Set, Optional

from karate_graph_analyzer.models import DependencyGraph, Node, Edge, DiffStatus

logger = logging.getLogger(__name__)

class GraphComparator:
    """Compares two DependencyGraphs and produces a diff-annotated graph."""

    def compare(self, base_graph: DependencyGraph, new_graph: DependencyGraph) -> DependencyGraph:
        """
        Compares new_graph against base_graph.
        Returns a new graph containing elements from both, annotated with DiffStatus.
        """
        logger.info(f"Comparing new graph '{new_graph.project_name}' against base '{base_graph.project_name}'")
        
        # We'll create a merged graph that contains everything
        # Status will be relative to base_graph
        
        diff_nodes: Dict[str, Node] = {}
        diff_edges: Dict[str, Edge] = {}
        
        # 1. Process all nodes in new_graph
        for node_id, node in new_graph.nodes.items():
            if node_id not in base_graph.nodes:
                # Node is NEW
                node.diff_status = DiffStatus.ADDED
            else:
                # Node exists in both, check if modified
                base_node = base_graph.nodes[node_id]
                if self._is_node_modified(base_node, node):
                    node.diff_status = DiffStatus.MODIFIED
                else:
                    node.diff_status = DiffStatus.UNCHANGED
            diff_nodes[node_id] = node
            
        # 2. Find nodes that were REMOVED (in base but not in new)
        for node_id, node in base_graph.nodes.items():
            if node_id not in new_graph.nodes:
                node.diff_status = DiffStatus.REMOVED
                diff_nodes[node_id] = node

        # 3. Process all edges in new_graph
        for edge_id, edge in new_graph.edges.items():
            if edge_id not in base_graph.edges:
                edge.diff_status = DiffStatus.ADDED
            else:
                edge.diff_status = DiffStatus.UNCHANGED
            diff_edges[edge_id] = edge
            
        # 4. Find edges that were REMOVED
        for edge_id, edge in base_graph.edges.items():
            if edge_id not in new_graph.edges:
                edge.diff_status = DiffStatus.REMOVED
                diff_edges[edge_id] = edge

        return DependencyGraph(
            project_name=f"Diff_{base_graph.project_name}_vs_{new_graph.project_name}",
            nodes=diff_nodes,
            edges=diff_edges,
            cycles=new_graph.cycles # Use cycles from new graph
        )

    def _is_node_modified(self, node_a: Node, node_b: Node) -> bool:
        """Heuristic to determine if a node has meaningfully changed."""
        # Check if type or basic metadata changed
        if node_a.type != node_b.type:
            return True
        
        # Check if tags changed
        if set(node_a.tags) != set(node_b.tags):
            return True
            
        # Check if file path or line number changed significantly
        if node_a.metadata.file_path != node_b.metadata.file_path:
            return True
            
        return False
