"""
Analysis Expert Module.

Provides high-level architectural insights and health checks for Karate projects.
"""

import logging
from typing import Dict, List, Set, Tuple
import networkx as nx

from karate_graph_analyzer.models import (
    DependencyGraph,
    NodeType,
    Node,
)

logger = logging.getLogger(__name__)


class AnalysisExpert:
    """Expert system for analyzing graph health and patterns."""

    def __init__(self, graph: DependencyGraph, nx_graph: nx.DiGraph) -> None:
        """Initialize with dependency graph and its NetworkX representation.

        Args:
            graph: The high-level DependencyGraph object
            nx_graph: The underlying NetworkX DiGraph
        """
        self.graph = graph
        self.nx_graph = nx_graph

    def find_orphans(self) -> List[Node]:
        """Find components that are defined but never used by any Test Case.
        
        Returns:
            List of orphan nodes
        """
        orphans = []
        
        # We only care about "implementation" nodes: API, PAGE, ACTION, WORKFLOW, SCENARIO
        target_types = {
            NodeType.API, 
            NodeType.PAGE, 
            NodeType.ACTION, 
            NodeType.WORKFLOW, 
            NodeType.SCENARIO,
            NodeType.DATABASE,
            NodeType.LOCATOR,
            NodeType.JAVA_CLASS,
            NodeType.JAVA_METHOD,
            NodeType.JAVASCRIPT,
            NodeType.JS_FUNCTION
        }
        
        for node_id, node in self.graph.nodes.items():
            if node.type not in target_types:
                continue
            
            # Check in-degree: nodes with 0 incoming edges are potential orphans
            # if they are not the entry point (Test Cases are usually entry points)
            if self.nx_graph.in_degree(node_id) == 0:
                # Test Cases are allowed to have 0 in-degree as they are roots
                if node.type != NodeType.TEST_CASE:
                    orphans.append(node)
        
        return orphans

    def find_redundant_apis(self) -> Dict[str, List[Node]]:
        """Find API definitions that appear to be duplicates.
        
        Returns:
            Dict mapping endpoint key to list of duplicate nodes
        """
        duplicates = {}
        api_map: Dict[str, List[Node]] = {}
        
        for node in self.graph.nodes.values():
            if node.type == NodeType.API:
                # Use URL + Method as key
                method = node.metadata.additional_data.get("http_method", "GET")
                # Use path_template or full_url as fallback, NOT node.name (which is now just the method)
                path = node.metadata.additional_data.get("path_template") or \
                       node.metadata.additional_data.get("full_url") or \
                       node.name
                
                key = f"{method} {path}"
                if key not in api_map:
                    api_map[key] = []
                api_map[key].append(node)
        
        # Filter only those with more than one definition
        for key, nodes in api_map.items():
            if len(nodes) > 1:
                duplicates[key] = nodes
                
        return duplicates

    def analyze_complexity(self, top_n: int = 5) -> List[Tuple[Node, int]]:
        """Identify Test Cases with high complexity (many dependencies).
        
        Returns:
            List of (Node, complexity_score) tuples
        """
        complexity_scores = []
        
        for node_id, node in self.graph.nodes.items():
            if node.type == NodeType.TEST_CASE:
                # Complexity = number of descendants (transitive dependencies)
                descendants = nx.descendants(self.nx_graph, node_id)
                complexity_scores.append((node, len(descendants)))
        
        # Sort by complexity descending
        complexity_scores.sort(key=lambda x: x[1], reverse=True)
        return complexity_scores[:top_n]

    def get_health_summary(self) -> Dict:
        """Get an aggregate health report for the project."""
        orphans = self.find_orphans()
        duplicates = self.find_redundant_apis()
        top_complex = self.analyze_complexity()
        
        # Check for cycles
        cycles = list(nx.simple_cycles(self.nx_graph))
        
        return {
            "orphan_count": len(orphans),
            "redundant_api_count": len(duplicates),
            "cycle_count": len(cycles),
            "top_complex_test_cases": [
                {"name": node.name, "score": score, "id": node.id}
                for node, score in top_complex
            ],
            "health_score": self._calculate_health_score(len(orphans), len(duplicates), len(cycles))
        }

    def _calculate_health_score(self, orphans: int, dups: int, cycles: int) -> float:
        """Calculate a 0-100 score based on issues found."""
        score = 100.0
        score -= min(30, orphans * 2)  # Max 30 points off for orphans
        score -= min(30, dups * 5)     # Max 30 points off for dups
        score -= min(40, cycles * 20)  # Max 40 points off for cycles
        return max(0.0, score)
