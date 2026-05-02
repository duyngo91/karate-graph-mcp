"""
Dependency Linker.

Handles the logic for linking dependencies between nodes, including
resolving call read() dependencies and building API hierarchies.
"""

import re
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from karate_graph_analyzer.models import (
    Dependency,
    DependencyType,
    NodeMetadata,
    NodeType,
)
from karate_graph_analyzer.utils.path_resolver import PathResolver


if TYPE_CHECKING:
    from karate_graph_analyzer.core.context import AnalysisContext


class DependencyLinker:
    """Handles linking of dependencies and building complex node structures."""

    def __init__(self, nx_builder, context: Optional["AnalysisContext"] = None, path_classifier: Optional[Any] = None, ignored_files: Optional[set] = None) -> None:
        """Initialize with a NetworkXBuilder instance.

        Args:
            nx_builder: NetworkXBuilder instance for graph operations
            context: Optional AnalysisContext for configuration and services
            path_classifier: Optional PathClassifier for component classification
            ignored_files: Optional set of normalized paths to ignore
        """
        self.nx_builder = nx_builder
        self.context = context
        self.path_classifier = path_classifier
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
        
        # Add business domain classification for the newly created node
        if self.path_classifier:
            # For file nodes, identity is the path
            feature = self.path_classifier.detect_business_domain(identity)
            # Access the actual node in graph to update its metadata
            if node_id in self.nx_builder.graph.nodes:
                # metadata is stored as a dict in the graph by NetworkXBuilder
                self.nx_builder.graph.nodes[node_id]['metadata']['additional_data']['feature'] = feature
                
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
            DependencyType.DATA: NodeType.DATA,
        }

        if dep.type == DependencyType.SETUP:
            return self.nx_builder.get_test_case_id(
                project_name, 
                dep.parameters.get("file_path"), 
                dep.parameters.get("setup_line_number"), 
                dep.target
            )

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
            category=self.path_classifier.classify_component_category(file_path) if self.path_classifier else ComponentCategory.UNKNOWN,
            environment_variants=[dep.parameters.get("physical_url")] if dep.parameters.get("physical_url") else [],
            additional_data=dep.parameters,
        )
        
        # Add business domain classification
        if self.path_classifier and file_path:
            feature = self.path_classifier.detect_business_domain(file_path)
            metadata.additional_data['feature'] = feature
        
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
            NodeType.DATA: self.nx_builder.add_data_node,
        }
        return mapping.get(node_type)

    def _handle_tag_subnode(self, parent_id: str, parent_type: NodeType, path: str, tag: str, metadata: NodeMetadata, node_map: Dict, dep_type: DependencyType, display_name: Optional[str] = None) -> str:
        """Handle creation of Scenario/Action nodes attached to parent file nodes."""
        is_page = parent_type == NodeType.PAGE
        sub_type = NodeType.ACTION if is_page else NodeType.SCENARIO
        
        # Normalize tag (this is the unique ID tag)
        clean_tag = tag if tag.startswith('@') else f"@{tag}"
        
        # Skip technical/metadata tags for node creation
        if self.context and self.context.tag_manager:
            if self.context.tag_manager.is_metadata_tag(clean_tag):
                return parent_id
        elif hasattr(self, 'config') and hasattr(self.config, 'is_metadata_tag'):
             if self.config.is_metadata_tag(clean_tag):
                return parent_id

        # IDENTITY is strictly based on the tag
        identity = f"{path}#{clean_tag}"
        
        # DISPLAY NAME
        name_to_use = display_name or clean_tag
        if not display_name and metadata.additional_data.get("scenario_name"):
            name_to_use = f"{clean_tag} - {metadata.additional_data['scenario_name']}"

        key = (sub_type, identity)
        if key in node_map:
            sub_node_id = node_map[key]
        else:
            if is_page:
                sub_node_id = self.nx_builder.add_action_node(name_to_use, path, metadata)
            else:
                sub_node_id = self.nx_builder.add_scenario_node(name_to_use, path, metadata)
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
        endpoint_clean = endpoint.strip()
        domain = None
        
        # Handle protocol
        protocol = ""
        if "://" in endpoint_clean:
            parts = endpoint_clean.split("://", 1)
            protocol = parts[0] + "://"
            endpoint_clean = parts[1]
            
        if endpoint_clean.startswith('/'):
            domain, path = None, endpoint_clean
        else:
            parts = endpoint_clean.split('/', 1)
            first_part = parts[0]
            path = '/' + parts[1] if len(parts) > 1 else ""
            
            # Use global reverse mapping to resolve physical domain back to variable
            if first_part and self.context and self.context.config:
                rev_map = self.context.config.global_reverse_mapping
                if rev_map:
                    # Try with protocol if we found one
                    if protocol:
                        target = f"{protocol}{first_part}"
                        # Check for exact or prefix match
                        for phys, logical in sorted(rev_map.items(), key=lambda x: len(x[0]), reverse=True):
                            if target.startswith(phys):
                                domain = f"${{{logical}}}"
                                break
                    
                    # Fallback to standard protocols if not resolved
                    if not domain:
                        for p in ["https://", "http://"]:
                            target = f"{p}{first_part}"
                            for phys, logical in sorted(rev_map.items(), key=lambda x: len(x[0]), reverse=True):
                                if target.startswith(phys):
                                    domain = f"${{{logical}}}"
                                    break
                            if domain: break
            
            if not domain:
                if '.' in first_part or first_part.startswith('${'):
                    domain = first_part
                else:
                    # No clear domain, treat first part as path
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
            
        # Filter out dynamic path params like {id} or {orderId}, but KEEP ${varName} Karate variables
        # - Dynamic params: {xxx}   → remove (they vary per request)
        # - Karate vars:   ${xxx}   → keep (they represent logical environments/domains)
        static_segments = [seg for seg in segments if not re.search(r'(?<!\$)\{[^}]+\}', seg)]
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
        
        tag_str = ""
        if self.context and self.context.tag_manager:
            tag_str = self.context.tag_manager.get_display_tag(tags)
        
        if scenario_name.strip():
            return f"{tag_str} - {scenario_name}" if tag_str else scenario_name
        return tag_str

    def _build_api_group_chain(self, segments: List[str], base_url: str, metadata: NodeMetadata, node_map: Dict) -> Optional[str]:
        parent_id = None
        for i, segment in enumerate(segments):
            # cumulative_path must include ALL segments from root to current
            # to avoid key collision between domain-prefixed and path-only hierarchies
            cumulative_path = '/'.join(segments[:i+1])
            node_key = (NodeType.API_GROUP, cumulative_path)
            
            if node_key in node_map:
                current_id = node_map[node_key]
            else:
                # Display name: always use the segment (e.g. "${t24Url}", "api", "v2")
                # base_url is only stored as metadata for reference, not as the node label
                display_name = segment
                additional_data = {
                    "level": i,
                    "segment": segment,
                    "base_url": base_url if i == 0 else None,
                    "cumulative_segment": cumulative_path
                }
                
                # Check for environment-specific URLs for domain nodes
                if i == 0 and self.context and self.context.project and self.context.project.parser_config:
                    var_name = segment.replace("${", "").replace("}", "")
                    env_map = self.context.project.parser_config.env_url_mapping.get(var_name)
                    if not env_map: # Try with original segment just in case
                        env_map = self.context.project.parser_config.env_url_mapping.get(segment)
                        
                    if env_map:
                        additional_data["environments"] = env_map

                group_meta = NodeMetadata(
                    file_path=None, line_number=None, jira_tags=[], project_name=metadata.project_name,
                    additional_data=additional_data
                )
                current_id = self.nx_builder.add_api_group_node(display_name, group_meta)
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
