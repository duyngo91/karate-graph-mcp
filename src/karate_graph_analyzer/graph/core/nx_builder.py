"""
NetworkX Graph Builder.

Handles low-level graph manipulation using NetworkX, including
adding nodes, edges, and generating unique IDs.
"""

from typing import Dict, List, Optional
import networkx as nx
import logging
import hashlib

from karate_graph_analyzer.models import (
    DependencyType,
    NodeMetadata,
    NodeType,
    Scenario,
)

logger = logging.getLogger(__name__)


class NetworkXBuilder:
    """Handles low-level NetworkX graph operations."""

    def __init__(self, graph: Optional[nx.DiGraph] = None) -> None:
        """Initialize with an existing graph or create a new one.

        Args:
            graph: Optional existing NetworkX DiGraph
        """
        self.graph: nx.DiGraph = graph if graph is not None else nx.DiGraph()
        self._node_counter: Dict[str, int] = {}  # Track node IDs by type

    def update_node_name(self, node_id: str, new_name: str) -> None:
        """Update the display name of an existing node."""
        if node_id in self.graph.nodes:
            self.graph.nodes[node_id]["name"] = new_name

    def update_node_metadata(self, node_id: str, additional_metadata: dict) -> None:
        """Update or add to the metadata of an existing node."""
        if node_id in self.graph.nodes:
            node = self.graph.nodes[node_id]
            if "metadata" not in node:
                node["metadata"] = {"additional_data": {}}
            
            # Update additional_data safely
            if "additional_data" not in node["metadata"]:
                node["metadata"]["additional_data"] = {}
                
            node["metadata"]["additional_data"].update(additional_metadata)

    def _generate_node_id(self, node_type: NodeType) -> str:
        """Generate unique node ID for a given node type.

        Args:
            node_type: Type of node

        Returns:
            Unique node ID string
        """
        # Use short prefixes for node types
        prefix_map = {
            NodeType.TEST_CASE: "tc",
            NodeType.WORKFLOW: "wf",
            NodeType.COMMON: "com",
            NodeType.SCENARIO: "scn",
            NodeType.API: "api",
            NodeType.API_GROUP: "apig",
            NodeType.PAGE: "page",
            NodeType.ACTION: "act",
            NodeType.DATABASE: "db",
            NodeType.LOCATOR: "loc",
        }
        prefix = prefix_map.get(node_type, "node")
        
        # Increment counter for this type
        if prefix not in self._node_counter:
            self._node_counter[prefix] = 0
        self._node_counter[prefix] += 1
        
        return f"{prefix}_{self._node_counter[prefix]:04d}"

    def _generate_stable_node_id(self, node_type: NodeType, identity: str) -> str:
        """Generate a deterministic ID while preserving human-friendly prefixes."""
        prefix_map = {
            NodeType.TEST_CASE: "tc",
            NodeType.WORKFLOW: "wf",
            NodeType.COMMON: "com",
            NodeType.SCENARIO: "scn",
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
        
        display_name = scenario.name
        
        node_data = {
            "id": node_id,
            "type": NodeType.TEST_CASE,
            "name": display_name,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
            "scenario_type": scenario.type,
            "tags": scenario.tags,
            "original_name": scenario.name,
        }
        
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_workflow_node(self, name: str, metadata: NodeMetadata) -> str:
        """Add workflow node to graph."""
        identity = "|".join([metadata.project_name, NodeType.WORKFLOW.value, name])
        node_id = self._generate_stable_node_id(NodeType.WORKFLOW, identity)
        node_data = {
            "id": node_id,
            "type": NodeType.WORKFLOW,
            "name": name,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_common_node(self, name: str, metadata: NodeMetadata) -> str:
        """Add common service/API definition node to graph."""
        identity = "|".join([metadata.project_name, NodeType.COMMON.value, name])
        node_id = self._generate_stable_node_id(NodeType.COMMON, identity)
        node_data = {
            "id": node_id,
            "type": NodeType.COMMON,
            "name": name,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_api_node(self, endpoint: str, metadata: NodeMetadata) -> str:
        """Add API call node to graph."""
        identity = "|".join([
            metadata.project_name,
            NodeType.API.value,
            str(endpoint or ""),
            str(metadata.additional_data.get("full_url", "")),
            str(metadata.additional_data.get("http_method", "")),
            str(metadata.additional_data.get("path_template", "")),
        ])
        node_id = self._generate_stable_node_id(NodeType.API, identity)
        node_data = {
            "id": node_id,
            "type": NodeType.API,
            "name": endpoint,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id
    
    def add_api_group_node(self, group_name: str, metadata: NodeMetadata) -> str:
        """Add API group node to graph."""
        # Use the cumulative segment path from additional_data if available,
        # otherwise fall back to group_name + level. This prevents hash
        # collisions between same-named segments in different domain trees
        # (e.g. "api" segment appearing under both t24.com and ecommerce.api.com).
        cumulative_segment = metadata.additional_data.get("cumulative_segment", group_name)
        identity = "|".join([
            metadata.project_name,
            NodeType.API_GROUP.value,
            cumulative_segment,
            str(metadata.additional_data.get("level", "")),
        ])

        node_id = self._generate_stable_node_id(NodeType.API_GROUP, identity)
        node_data = {
            "id": node_id,
            "type": NodeType.API_GROUP,
            "name": group_name,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_page_node(self, page_path: str, metadata: NodeMetadata) -> str:
        """Add page object node to graph."""
        identity = "|".join([metadata.project_name, NodeType.PAGE.value, page_path])
        node_id = self._generate_stable_node_id(NodeType.PAGE, identity)
        node_data = {
            "id": node_id,
            "type": NodeType.PAGE,
            "name": page_path,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_database_node(self, operation: str, metadata: NodeMetadata) -> str:
        """Add database operation node to graph."""
        identity = "|".join([metadata.project_name, NodeType.DATABASE.value, operation])
        node_id = self._generate_stable_node_id(NodeType.DATABASE, identity)
        node_data = {
            "id": node_id,
            "type": NodeType.DATABASE,
            "name": operation,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id
    
    def add_locator_node(self, locator_path: str, metadata: NodeMetadata) -> str:
        """Add locator object node to graph."""
        identity = "|".join([metadata.project_name, NodeType.LOCATOR.value, locator_path])
        node_id = self._generate_stable_node_id(NodeType.LOCATOR, identity)
        node_data = {
            "id": node_id,
            "type": NodeType.LOCATOR,
            "name": locator_path,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": metadata.additional_data,
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id
    
    def add_scenario_node(self, scenario_tag: str, workflow_path: str, metadata: NodeMetadata) -> str:
        """Add scenario node to graph."""
        if not scenario_tag.startswith('@'):
            scenario_tag = f'@{scenario_tag}'
        identity = "|".join([metadata.project_name, NodeType.SCENARIO.value, workflow_path, scenario_tag])
        node_id = self._generate_stable_node_id(NodeType.SCENARIO, identity)
        
        node_data = {
            "id": node_id,
            "type": NodeType.SCENARIO,
            "name": scenario_tag,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": {
                    **metadata.additional_data,
                    "scenario_tag": scenario_tag,
                    "workflow_path": workflow_path,
                },
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id
    
    def add_action_node(self, action_tag: str, page_path: str, metadata: NodeMetadata) -> str:
        """Add action node to graph."""
        if not action_tag.startswith('@'):
            action_tag = f'@{action_tag}'
        identity = "|".join([metadata.project_name, NodeType.ACTION.value, page_path, action_tag])
        node_id = self._generate_stable_node_id(NodeType.ACTION, identity)
        
        node_data = {
            "id": node_id,
            "type": NodeType.ACTION,
            "name": action_tag,
            "metadata": {
                "file_path": metadata.file_path,
                "line_number": metadata.line_number,
                "jira_tags": metadata.jira_tags,
                "project_name": metadata.project_name,
                "additional_data": {
                    **metadata.additional_data,
                    "action_tag": action_tag,
                    "page_path": page_path,
                },
            },
        }
        self.graph.add_node(node_id, **node_data)
        return node_id

    def add_dependency(self, from_node: str, to_node: str, dep_type: DependencyType, line_number: Optional[int] = None) -> str:
        """Add directed edge representing dependency."""
        edge_id = f"edge_{from_node}_{to_node}_{dep_type.value}_{line_number or 0}"
        edge_data = {
            "id": edge_id,
            "from_node": from_node,
            "to_node": to_node,
            "type": dep_type,
            "line_number": line_number,
        }
        self.graph.add_edge(from_node, to_node, **edge_data)
        return edge_id

    def detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies using DFS."""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            self.graph.graph['cycles'] = cycles
            return cycles
        except Exception as e:
            logger.warning(f"Cycle detection failed: {e}")
            return []
