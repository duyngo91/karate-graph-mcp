"""
NetworkX Graph Builder implementation.

Handles the low-level construction of the NetworkX directed graph,
node ID generation, and metadata management.
"""

import hashlib
import logging
from typing import Dict, List, Optional, Any, Tuple
import networkx as nx

from karate_graph_analyzer.models import (
    DependencyType,
    NodeMetadata,
    NodeType,
    Scenario,
)

logger = logging.getLogger(__name__)


class NetworkXBuilder:
    """Specialized component for NetworkX graph operations.
    
    Implements the Builder pattern for graph construction.
    """

    def __init__(self) -> None:
        """Initialize builder with an empty directed graph."""
        self.graph = nx.DiGraph()
        self._node_counter: Dict[NodeType, int] = {}

    def _generate_stable_node_id(self, node_type: NodeType, identity: str) -> str:
        """Generate a stable, short node ID based on type and identity string."""
        prefix_map = {
            NodeType.TEST_CASE: "tc",
            NodeType.WORKFLOW: "wf",
            NodeType.COMMON: "com",
            NodeType.SCENARIO: "scen",
            NodeType.API: "api",
            NodeType.API_GROUP: "apig",
            NodeType.PAGE: "page",
            NodeType.ACTION: "act",
            NodeType.DATABASE: "db",
            NodeType.LOCATOR: "loc",
        }
        prefix = prefix_map.get(node_type, "node")
        digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"

    def _add_node_internal(self, node_id: str, node_type: NodeType, name: str, metadata: NodeMetadata, extra_data: Dict[str, Any] = None) -> str:
        """Centralized method to add a node to the graph with consistent data structure."""
        
        # Ensure tags are always present and filter out ALM2 tags
        raw_tags = metadata.additional_data.get("tags", [])
        tags = [t for t in raw_tags if not t.startswith("@ALM2:")]
        
        node_data = {
            "id": node_id,
            "type": node_type,
            "name": name,
            "tags": tags,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            }
        }
        
        # Merge extra data if provided (for backward compatibility or type-specific fields)
        if extra_data:
            node_data.update(extra_data)
            
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_test_case(self, scenario: Scenario, metadata: NodeMetadata) -> str:
        """Add test case node to graph."""
        identity = "|".join([
            metadata.project_name,
            NodeType.TEST_CASE.value,
            metadata.file_path or "",
            str(metadata.line_number or ""),
            scenario.name,
        ])
        node_id = self._generate_stable_node_id(NodeType.TEST_CASE, identity)
        
        extra = {
            "scenario_type": scenario.type,
            "original_name": scenario.name,
        }
        # Merge scenario tags with existing tags in additional_data (stable deduplication)
        existing_tags = metadata.additional_data.get("tags", [])
        metadata.additional_data["tags"] = list(dict.fromkeys(existing_tags + scenario.tags))
        
        return self._add_node_internal(node_id, NodeType.TEST_CASE, scenario.name, metadata, extra)

    def add_workflow_node(self, name: str, metadata: NodeMetadata) -> str:
        """Add workflow node to graph."""
        identity = "|".join([metadata.project_name, NodeType.WORKFLOW.value, name])
        node_id = self._generate_stable_node_id(NodeType.WORKFLOW, identity)
        return self._add_node_internal(node_id, NodeType.WORKFLOW, name, metadata)

    def add_common_node(self, name: str, metadata: NodeMetadata) -> str:
        """Add common service/API definition node to graph."""
        identity = "|".join([metadata.project_name, NodeType.COMMON.value, name])
        node_id = self._generate_stable_node_id(NodeType.COMMON, identity)
        return self._add_node_internal(node_id, NodeType.COMMON, name, metadata)

    def add_api_node(self, endpoint: str, metadata: NodeMetadata) -> str:
        """Add API call node to graph."""
        identity = "|".join([
            metadata.project_name,
            NodeType.API.value,
            endpoint,
            str(metadata.additional_data.get("http_method", "GET"))
        ])
        node_id = self._generate_stable_node_id(NodeType.API, identity)
        return self._add_node_internal(node_id, NodeType.API, endpoint, metadata)

    def add_api_group_node(self, group_name: str, metadata: NodeMetadata) -> str:
        """Add hierarchical API group node."""
        cumulative_segment = metadata.additional_data.get("cumulative_segment", group_name)
        identity = "|".join([
            metadata.project_name,
            NodeType.API_GROUP.value,
            cumulative_segment,
            str(metadata.additional_data.get("level", "")),
        ])
        node_id = self._generate_stable_node_id(NodeType.API_GROUP, identity)
        return self._add_node_internal(node_id, NodeType.API_GROUP, group_name, metadata)

    def add_page_node(self, page_path: str, metadata: NodeMetadata) -> str:
        """Add page object node to graph."""
        identity = "|".join([metadata.project_name, NodeType.PAGE.value, page_path])
        node_id = self._generate_stable_node_id(NodeType.PAGE, identity)
        return self._add_node_internal(node_id, NodeType.PAGE, page_path, metadata)

    def add_database_node(self, operation: str, metadata: NodeMetadata) -> str:
        """Add database operation node to graph."""
        identity = "|".join([metadata.project_name, NodeType.DATABASE.value, operation])
        node_id = self._generate_stable_node_id(NodeType.DATABASE, identity)
        return self._add_node_internal(node_id, NodeType.DATABASE, operation, metadata)

    def add_locator_node(self, locator_path: str, metadata: NodeMetadata) -> str:
        """Add locator file node to graph."""
        identity = "|".join([metadata.project_name, NodeType.LOCATOR.value, locator_path])
        node_id = self._generate_stable_node_id(NodeType.LOCATOR, identity)
        return self._add_node_internal(node_id, NodeType.LOCATOR, locator_path, metadata)

    def add_scenario_node(self, scenario_tag: str, workflow_path: str, metadata: NodeMetadata) -> str:
        """Add workflow scenario node to graph (@AddPayment, etc.)."""
        if not scenario_tag.startswith('@'):
            scenario_tag = f'@{scenario_tag}'
        identity = "|".join([metadata.project_name, NodeType.SCENARIO.value, workflow_path, scenario_tag])
        node_id = self._generate_stable_node_id(NodeType.SCENARIO, identity)
        
        # Ensure scenario info is in additional_data
        metadata.additional_data.update({
            "scenario_tag": scenario_tag,
            "workflow_path": workflow_path,
        })
        return self._add_node_internal(node_id, NodeType.SCENARIO, scenario_tag, metadata)

    def add_action_node(self, action_tag: str, page_path: str, metadata: NodeMetadata) -> str:
        """Add page action node to graph (@login, etc.)."""
        if not action_tag.startswith('@'):
            action_tag = f'@{action_tag}'
        identity = "|".join([metadata.project_name, NodeType.ACTION.value, page_path, action_tag])
        node_id = self._generate_stable_node_id(NodeType.ACTION, identity)
        
        # Ensure action info is in additional_data
        metadata.additional_data.update({
            "action_tag": action_tag,
            "page_path": page_path,
        })
        return self._add_node_internal(node_id, NodeType.ACTION, action_tag, metadata)

    def update_node_metadata(self, node_id: str, additional_data: Dict[str, Any]) -> None:
        """Update existing node's additional_data metadata."""
        if node_id in self.graph:
            node = self.graph.nodes[node_id]
            if "metadata" in node and "additional_data" in node["metadata"]:
                node["metadata"]["additional_data"].update(additional_data)
            
            # If tags are being updated via additional_data, sync them to the top level
            if "tags" in additional_data:
                node["tags"] = list(set(node.get("tags", []) + additional_data["tags"]))

    def add_dependency(self, from_node: str, to_node: str, dep_type: DependencyType, line_number: int = None) -> str:
        """Add a directed edge representing a dependency."""
        edge_id = f"edge_{from_node}_{to_node}_{dep_type.value}_{line_number or 0}"
        self.graph.add_edge(
            from_node,
            to_node,
            id=edge_id,
            from_node=from_node,
            to_node=to_node,
            type=dep_type,
            line_number=line_number,
        )
        return edge_id

    def detect_cycles(self) -> List[List[str]]:
        """Detect and return all cycles in the graph."""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            self.graph.graph['cycles'] = cycles
            return cycles
        except Exception as e:
            logger.error(f"Cycle detection failed: {e}")
            self.graph.graph['cycles'] = []
            return []
