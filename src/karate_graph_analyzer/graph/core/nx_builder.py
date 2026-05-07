"""
NetworkX Graph Builder implementation.

Handles the low-level construction of the NetworkX directed graph,
node ID generation, and metadata management.
"""

import os
import logging
import hashlib
import networkx as nx
from typing import Dict, List, Optional, Any, Set

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
            NodeType.JAVA_CLASS: "java",
            NodeType.JAVA_METHOD: "jvm",
        }
        prefix = prefix_map.get(node_type, "node")
        digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"

    def _add_node_internal(self, node_id: str, node_type: NodeType, name: str, metadata: NodeMetadata, extra_data: Dict[str, Any] = None) -> str:
        """Centralized method to add a node to the graph with consistent data structure.
        Handles merging if node already exists.
        """
        raw_tags = metadata.additional_data.get("tags", [])
        tags = [t for t in raw_tags if not t.startswith("@ALM2:")]

        if node_id in self.graph:
            # Merging Logic for duplicate logical nodes (e.g. multi-environment)
            node = self.graph.nodes[node_id]
            
            # If node was implicitly created by an edge, it will be empty
            if "metadata" not in node:
                # Re-initialize node data
                node.update({
                    "id": node_id,
                    "type": node_type,
                    "name": name,
                    "tags": tags,
                    "metadata": {
                        "file_path": metadata.file_path,
                        "line_number": metadata.line_number,
                        "jira_tags": metadata.jira_tags,
                        "project_name": metadata.project_name,
                        "category": metadata.category,
                        "flow": metadata.flow,
                        "environment_variants": metadata.environment_variants,
                        "additional_data": metadata.additional_data,
                    }
                })
                return node_id

            # 1. Merge tags
            existing_tags = node.get("tags", [])
            node["tags"] = list(dict.fromkeys(existing_tags + tags))
            
            # 2. Merge environment variants
            if hasattr(metadata, "environment_variants") and metadata.environment_variants:
                current_variants = node["metadata"].get("environment_variants", {})
                current_variants.update(metadata.environment_variants)
                node["metadata"]["environment_variants"] = current_variants
            
            # 3. Merge additional data
            if metadata.additional_data:
                node["metadata"]["additional_data"].update(metadata.additional_data)
                
            return node_id
        
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
                "category": metadata.category,
                "flow": metadata.flow,
                "environment_variants": metadata.environment_variants,
                "additional_data": metadata.additional_data,
            }
        }
        
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
        
        display_name = scenario.name
        if metadata.additional_data.get("display_jira_prefix", True) and scenario.jira_tags:
            jira_id = scenario.jira_tags[0].lstrip("@")
            display_name = f"[{jira_id}] {scenario.name}"

        return self._add_node_internal(node_id, NodeType.TEST_CASE, display_name, metadata, extra)

    def get_test_case_id(self, project_name: str, file_path: str, line_number: int, name: str) -> str:
        """Generate the stable ID for a test case without creating the node."""
        identity = "|".join([
            project_name,
            NodeType.TEST_CASE.value,
            file_path or "",
            str(line_number or ""),
            name,
        ])
        return self._generate_stable_node_id(NodeType.TEST_CASE, identity)

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

    def add_data_node(self, data_path: str, metadata: NodeMetadata) -> str:
        """Add external data file node (JSON/CSV) to graph."""
        identity = "|".join([metadata.project_name, NodeType.DATA.value, data_path])
        node_id = self._generate_stable_node_id(NodeType.DATA, identity)
        return self._add_node_internal(node_id, NodeType.DATA, data_path, metadata)

    def add_scenario_node(self, display_name: str, workflow_path: str, metadata: NodeMetadata, identity_tag: Optional[str] = None) -> str:
        """Add workflow scenario node to graph (@AddPayment, etc.)."""
        # Identity is based on the stable tag if provided, otherwise the display name
        tag_for_id = identity_tag or display_name
        if not tag_for_id.startswith('@'):
            tag_for_id = f'@{tag_for_id}'
            
        identity = "|".join([metadata.project_name, NodeType.SCENARIO.value, workflow_path, tag_for_id])
        node_id = self._generate_stable_node_id(NodeType.SCENARIO, identity)
        
        # Ensure scenario info is in additional_data
        metadata.additional_data.update({
            "scenario_tag": tag_for_id,
            "workflow_path": workflow_path,
        })
        return self._add_node_internal(node_id, NodeType.SCENARIO, display_name, metadata)

    def add_action_node(self, display_name: str, page_path: str, metadata: NodeMetadata, identity_tag: Optional[str] = None) -> str:
        """Add page action node to graph (@login, etc.)."""
        # Identity is based on the stable tag if provided, otherwise the display name
        tag_for_id = identity_tag or display_name
        if not tag_for_id.startswith('@'):
            tag_for_id = f'@{tag_for_id}'
            
        identity = "|".join([metadata.project_name, NodeType.ACTION.value, page_path, tag_for_id])
        node_id = self._generate_stable_node_id(NodeType.ACTION, identity)
        
        # Ensure action info is in additional_data
        metadata.additional_data.update({
            "action_tag": tag_for_id,
            "page_path": page_path,
        })
        return self._add_node_internal(node_id, NodeType.ACTION, display_name, metadata)

    def add_folder_node(self, folder_path: str, metadata: NodeMetadata) -> str:
        """Add a folder node to the structural layer."""
        identity = "|".join([metadata.project_name, NodeType.FOLDER.value, folder_path])
        node_id = f"folder_{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:12]}"
        return self._add_node_internal(node_id, NodeType.FOLDER, os.path.basename(folder_path) or folder_path, metadata)

    def add_file_node(self, file_path: str, metadata: NodeMetadata) -> str:
        """Add a file node to the structural layer."""
        identity = "|".join([metadata.project_name, NodeType.FILE.value, file_path])
        node_id = f"file_{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:12]}"
        return self._add_node_internal(node_id, NodeType.FILE, os.path.basename(file_path), metadata)

    def add_java_class_node(self, class_path: str, metadata: NodeMetadata) -> str:
        """Add Java class node to graph."""
        identity = "|".join([metadata.project_name, NodeType.JAVA_CLASS.value, class_path])
        node_id = self._generate_stable_node_id(NodeType.JAVA_CLASS, identity)
        return self._add_node_internal(node_id, NodeType.JAVA_CLASS, class_path, metadata)

    def add_java_method_node(self, class_path: str, method_name: str, metadata: NodeMetadata) -> str:
        """Add Java method node to graph."""
        identity = "|".join([metadata.project_name, NodeType.JAVA_METHOD.value, f"{class_path}.{method_name}"])
        node_id = self._generate_stable_node_id(NodeType.JAVA_METHOD, identity)
        return self._add_node_internal(node_id, NodeType.JAVA_METHOD, f"{class_path}.{method_name}", metadata)

    def update_node_metadata(self, node_id: str, updates: Dict[str, Any]) -> None:
        """Update existing node's metadata (additional_data, variants, etc.)."""
        if node_id in self.graph:
            node = self.graph.nodes[node_id]
            if "metadata" not in node:
                return
                
            # 1. Update additional_data
            if "additional_data" in updates:
                node["metadata"]["additional_data"].update(updates["additional_data"])
            elif any(k in updates for k in ["descriptive_name", "scenario_name", "scenario_tags"]):
                # Legacy support for direct key updates
                node["metadata"]["additional_data"].update({
                    k: v for k, v in updates.items() if k in ["descriptive_name", "scenario_name", "scenario_tags"]
                })
            
            # 2. Update environment_variants
            if "environment_variants" in updates and updates["environment_variants"]:
                current_variants = node["metadata"].get("environment_variants", {})
                current_variants.update(updates["environment_variants"])
                node["metadata"]["environment_variants"] = current_variants
            
            # 3. Sync tags if present
            if "tags" in updates:
                node["tags"] = list(set(node.get("tags", []) + updates["tags"]))

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
