"""
Dependency Linker.

Handles the logic for linking dependencies between nodes, including
resolving call read() dependencies and building API hierarchies.
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from karate_graph_analyzer.models import (
    Dependency,
    DependencyType,
    NodeMetadata,
    NodeType,
)
from karate_graph_analyzer.utils.path_resolver import PathResolver


class DependencyLinker:
    """Handles linking of dependencies and building complex node structures."""

    def __init__(self, nx_builder, ignored_files: Optional[set] = None) -> None:
        """Initialize with a NetworkXBuilder instance.

        Args:
            nx_builder: NetworkXBuilder instance for graph operations
            ignored_files: Optional set of normalized paths to ignore
        """
        self.nx_builder = nx_builder
        self.ignored_files = ignored_files or set()

    def normalize_path(self, path: str) -> str:
        """Proxy to PathResolver for backward compatibility."""
        return PathResolver.normalize_path(path)

    def _get_or_create_node(
        self, 
        node_type: NodeType, 
        identity: str, 
        metadata: NodeMetadata, 
        node_map: Dict[Tuple, str],
        creation_func,
        **kwargs
    ) -> str:
        """Generic helper to handle the common 'get-from-map or create-and-add-to-map' pattern."""
        key = (node_type, identity)
        if key in node_map:
            return node_map[key]
        
        node_id = creation_func(identity, metadata, **kwargs)
        node_map[key] = node_id
        return node_id

    def get_or_create_dependency_node(
        self, 
        dep: Dependency, 
        project_name: str,
        node_map: Dict[Tuple, str],
        context: Any = None
    ) -> str:
        """Get existing dependency node or create a new one."""
        node_type_map = {
            DependencyType.WORKFLOW: NodeType.WORKFLOW,
            DependencyType.API: NodeType.API,
            DependencyType.PAGE: NodeType.PAGE,
            DependencyType.DATABASE: NodeType.DATABASE,
            DependencyType.LOCATOR: NodeType.LOCATOR,
            DependencyType.COMMON: NodeType.COMMON,
        }
        
        node_type = node_type_map[dep.type]
        norm_target = self.normalize_path(dep.target)
        
        # Check if target is ignored
        if norm_target in self.ignored_files:
            return None
            
        # Resolve path to absolute if possible
        abs_path = dep.target
        if context and dep.type in [DependencyType.WORKFLOW, DependencyType.PAGE, DependencyType.LOCATOR, DependencyType.COMMON]:
            abs_path = PathResolver.resolve(dep.target, context)
            
        # Determine file_path for metadata
        file_path = abs_path if dep.type in [DependencyType.WORKFLOW, DependencyType.PAGE, DependencyType.LOCATOR, DependencyType.COMMON] else dep.parameters.get("file_path")
            
        metadata = NodeMetadata(
            file_path=file_path,
            line_number=dep.line_number,
            jira_tags=[],
            project_name=project_name,
            additional_data=dep.parameters,
        )
        
        # API handled separately due to hierarchy
        if dep.type == DependencyType.API:
            return self.create_api_hierarchy(dep.target, metadata, node_map)
            
        # Common pattern for WORKFLOW, COMMON, PAGE, LOCATOR, DATABASE
        node_id = self._get_or_create_node(
            node_type, 
            norm_target, 
            metadata, 
            node_map,
            self._get_creation_func(node_type)
        )
        
        # Special handling for Scenario/Action tags
        scenario_tag = dep.parameters.get('scenario_tag')
        if scenario_tag and node_type in [NodeType.WORKFLOW, NodeType.COMMON, NodeType.PAGE]:
            return self._handle_tag_subnode(node_id, node_type, norm_target, scenario_tag, metadata, node_map, dep.type)
            
        return node_id

    def _get_creation_func(self, node_type: NodeType):
        """Map NodeType to NetworkXBuilder method."""
        mapping = {
            NodeType.WORKFLOW: self.nx_builder.add_workflow_node,
            NodeType.COMMON: self.nx_builder.add_common_node,
            NodeType.PAGE: self.nx_builder.add_page_node,
            NodeType.LOCATOR: self.nx_builder.add_locator_node,
            NodeType.DATABASE: self.nx_builder.add_database_node,
        }
        return mapping.get(node_type)

    def _handle_tag_subnode(self, parent_id: str, parent_type: NodeType, path: str, tag: str, metadata: NodeMetadata, node_map: Dict, dep_type: DependencyType) -> str:
        """Handle creation of Scenario/Action nodes attached to parent file nodes."""
        is_page = parent_type == NodeType.PAGE
        sub_type = NodeType.ACTION if is_page else NodeType.SCENARIO
        
        # Normalize tag
        clean_tag = tag if tag.startswith('@') else f"@{tag}"
        identity = f"{path}#{clean_tag}"
        
        key = (sub_type, identity)
        if key in node_map:
            sub_node_id = node_map[key]
        else:
            if is_page:
                sub_node_id = self.nx_builder.add_action_node(tag, path, metadata)
            else:
                sub_node_id = self.nx_builder.add_scenario_node(tag, path, metadata)
            node_map[key] = sub_node_id
            
        # Link to parent
        if not self.nx_builder.graph.has_edge(parent_id, sub_node_id):
            self.nx_builder.add_dependency(parent_id, sub_node_id, dep_type)
            
        return sub_node_id

    def parse_api_hierarchy(self, endpoint: str) -> List[str]:
        """Parse API endpoint into segments (domain + path parts)."""
        if not endpoint or endpoint == '/':
            return []
            
        endpoint_clean = endpoint.replace('http://', '').replace('https://', '')
        if endpoint_clean.startswith('localhost'):
            endpoint_clean = endpoint_clean[len('localhost'):].lstrip(':0123456789')
            
        if not endpoint_clean or endpoint_clean == '/':
            return []
            
        if endpoint_clean.startswith('/'):
            domain, path = None, endpoint_clean
        else:
            parts = endpoint_clean.split('/', 1)
            first_part = parts[0]
            if '.' in first_part or first_part.startswith('${'):
                domain = first_part
                path = '/' + parts[1] if len(parts) > 1 else ''
            else:
                domain, path = None, '/' + endpoint_clean
        
        segments = []
        if domain: segments.append(domain)
        if path: segments.extend([p for p in path.split('/') if p])
        return segments

    def create_api_hierarchy(self, endpoint: str, metadata: NodeMetadata, node_map: Dict[Tuple, str]) -> str:
        """Create hierarchical API structure and return leaf node ID."""
        http_method = metadata.additional_data.get("http_method", "GET")
        path_template = metadata.additional_data.get("path_template", "")
        base_url = metadata.additional_data.get("base_url", "")
        
        target_url = f"{base_url}{path_template}" if (path_template and base_url) else endpoint
        segments = self.parse_api_hierarchy(target_url)
        
        if not segments:
            return self.create_single_api_node(endpoint, metadata, node_map)
            
        static_segments = [seg for seg in segments if '{' not in seg]
        descriptive_name = self._build_descriptive_api_name(metadata)
        
        # Display name for leaf node
        display_name = endpoint
        if path_template and "{" in path_template:
            match = re.search(r'\{([^}]+)\}', path_template)
            if match: display_name = f"{endpoint} {{{match.group(1)}}}"
        
        if descriptive_name:
            metadata.additional_data["descriptive_name"] = descriptive_name
        
        parent_node_id = self._build_api_group_chain(static_segments, base_url, metadata, node_map)
        
        # Handle Dynamic methods and leaf node creation
        return self._get_or_create_leaf_api_node(endpoint, http_method, display_name, metadata, parent_node_id, node_map)

    def _build_descriptive_api_name(self, metadata: NodeMetadata) -> str:
        scenario_name = metadata.additional_data.get("scenario_name", "")
        tags = metadata.additional_data.get("scenario_tags", [])
        tag_str = (tags[0] if tags[0].startswith("@") else f"@{tags[0]}") if tags else ""
        
        if scenario_name.strip():
            return f"{tag_str} - {scenario_name}" if tag_str else scenario_name
        return tag_str

    def _build_api_group_chain(self, segments: List[str], base_url: str, metadata: NodeMetadata, node_map: Dict) -> Optional[str]:
        parent_id = None
        for i, segment in enumerate(segments):
            cumulative_path = '/'.join(segments[:i+1])
            node_key = (NodeType.API_GROUP, cumulative_path)
            
            if node_key in node_map:
                current_id = node_map[node_key]
            else:
                group_meta = NodeMetadata(
                    file_path=None, line_number=None, jira_tags=[], project_name=metadata.project_name,
                    additional_data={"level": i, "segment": segment, "base_url": base_url if i == 0 else None, "cumulative_segment": cumulative_path}
                )
                current_id = self.nx_builder.add_api_group_node(base_url if (i == 0 and base_url) else segment, group_meta)
                node_map[node_key] = current_id

            if parent_id and not self.nx_builder.graph.has_edge(parent_id, current_id):
                self.nx_builder.add_dependency(parent_id, current_id, DependencyType.API)
            parent_id = current_id
        return parent_id

    def _get_or_create_leaf_api_node(self, endpoint: str, method: str, display: str, metadata: NodeMetadata, parent_id: str, node_map: Dict) -> str:
        # Check for dynamic method existing concrete match
        if method == "DYNAMIC":
            existing = next((k for k in node_map if k[0] == NodeType.API and k[1].startswith(f"{endpoint}#") and not k[1].endswith("#DYNAMIC")), None)
            if existing:
                leaf_id = node_map[existing]
                self._enrich_api_metadata(leaf_id, metadata)
                self._link_to_parent(parent_id, leaf_id)
                return leaf_id

        node_key = (NodeType.API, f"{endpoint}#{method}")
        if node_key in node_map:
            leaf_id = node_map[node_key]
            self._enrich_api_metadata(leaf_id, metadata)
        else:
            leaf_id = self.nx_builder.add_api_node(display, metadata)
            node_map[node_key] = leaf_id
        
        self._link_to_parent(parent_id, leaf_id)
        return leaf_id

    def _enrich_api_metadata(self, node_id: str, metadata: NodeMetadata):
        desc = metadata.additional_data.get("descriptive_name")
        if desc:
            self.nx_builder.update_node_metadata(node_id, {
                "descriptive_name": desc,
                "scenario_name": metadata.additional_data.get("scenario_name"),
                "scenario_tags": metadata.additional_data.get("scenario_tags")
            })

    def _link_to_parent(self, parent_id: str, child_id: str):
        if parent_id and not self.nx_builder.graph.has_edge(parent_id, child_id):
            self.nx_builder.add_dependency(parent_id, child_id, DependencyType.API)

    def create_single_api_node(self, endpoint: str, metadata: NodeMetadata, node_map: Dict[Tuple, str]) -> str:
        """Create a single API node without hierarchy."""
        return self._get_or_create_node(NodeType.API, endpoint, metadata, node_map, self.nx_builder.add_api_node)
