"""
Dependency Linker.

Handles the logic for linking dependencies between nodes, including
resolving call read() dependencies and building API hierarchies.
"""

from typing import Dict, List, Optional, Tuple
from karate_graph_analyzer.models import (
    Dependency,
    DependencyType,
    NodeMetadata,
    NodeType,
)


class DependencyLinker:
    """Handles linking of dependencies and building complex node structures."""

    def __init__(self, nx_builder) -> None:
        """Initialize with a NetworkXBuilder instance.

        Args:
            nx_builder: NetworkXBuilder instance for graph operations
        """
        self.nx_builder = nx_builder

    def normalize_path(self, path: str) -> str:
        """Normalize feature file path for consistent node keys."""
        if not path:
            return ""
        
        # 1. Convert to forward slashes
        norm = path.replace("\\", "/")
        
        # 2. Strip prefixes like classpath: or file:
        if norm.startswith("classpath:/"):
            norm = norm[11:]
        elif norm.startswith("classpath:"):
            norm = norm[10:]
        elif norm.startswith("file:"):
            norm = norm[5:].lstrip("/")
        
        # 3. Handle absolute paths by looking for common root markers
        markers = [
            "src/test/java/",
            "src/test/resources/",
            "src/main/resources/",
            "features/",
        ]
        for marker in markers:
            if marker in norm:
                norm = norm.split(marker, 1)[-1]
                break

        # 4. Strip any leading slashes remaining after prefix removal
        norm = norm.lstrip("/")

        # 5. Ensure .feature extension if it's likely a feature file path
        if "." not in norm.split("/")[-1] and not norm.endswith("/") and norm:
            norm += ".feature"
        
        return norm

    def get_or_create_dependency_node(
        self, 
        dep: Dependency, 
        project_name: str,
        node_map: Dict[Tuple, str]
    ) -> str:
        """Get existing dependency node or create a new one."""
        node_type_map = {
            DependencyType.WORKFLOW: NodeType.WORKFLOW,
            DependencyType.API: NodeType.API,
            DependencyType.PAGE: NodeType.PAGE,
            DependencyType.DATABASE: NodeType.DATABASE,
            DependencyType.LOCATOR: NodeType.LOCATOR,
            DependencyType.COMMON: NodeType.WORKFLOW, # Fallback
        }
        
        node_type = node_type_map[dep.type]
        
        # Create metadata
        if dep.type in [DependencyType.WORKFLOW, DependencyType.PAGE, DependencyType.LOCATOR]:
            file_path = dep.target
        elif dep.type == DependencyType.API:
            file_path = dep.parameters.get("file_path")
        else:
            file_path = None
            
        metadata = NodeMetadata(
            file_path=file_path,
            line_number=dep.line_number,
            jira_tags=[],
            project_name=project_name,
            additional_data=dep.parameters,
        )
        
        # Create node based on type
        norm_target = self.normalize_path(dep.target)
        
        if dep.type in [DependencyType.WORKFLOW, DependencyType.COMMON]:
            node_key = (node_type, norm_target)
            if node_key in node_map:
                workflow_node_id = node_map[node_key]
            else:
                workflow_node_id = self.nx_builder.add_workflow_node(norm_target, metadata)
                node_map[node_key] = workflow_node_id
            
            scenario_tag = dep.parameters.get('scenario_tag')
            if scenario_tag:
                scenario_key = (NodeType.SCENARIO, f"{norm_target}#{scenario_tag}")
                if scenario_key in node_map:
                    scenario_node_id = node_map[scenario_key]
                else:
                    scenario_node_id = self.nx_builder.add_scenario_node(
                        scenario_tag=scenario_tag,
                        workflow_path=norm_target,
                        metadata=metadata
                    )
                    node_map[scenario_key] = scenario_node_id
                    
                    if not self.nx_builder.graph.has_edge(workflow_node_id, scenario_node_id):
                        self.nx_builder.add_dependency(workflow_node_id, scenario_node_id, dep.type)
                return scenario_node_id
            return workflow_node_id
            
        elif dep.type == DependencyType.API:
            return self.create_api_hierarchy(dep.target, metadata, node_map)
            
        elif dep.type == DependencyType.PAGE:
            node_key = (node_type, norm_target)
            if node_key in node_map:
                page_node_id = node_map[node_key]
            else:
                page_node_id = self.nx_builder.add_page_node(norm_target, metadata)
                node_map[node_key] = page_node_id
            
            action_tag = dep.parameters.get('scenario_tag')
            if action_tag:
                # Normalize action tag (ensure it starts with @ for the key)
                key_tag = action_tag if action_tag.startswith('@') else f"@{action_tag}"
                action_key = (NodeType.ACTION, f"{norm_target}#{key_tag}")
                
                if action_key in node_map:
                    action_node_id = node_map[action_key]
                else:
                    action_node_id = self.nx_builder.add_action_node(
                        action_tag=action_tag,
                        page_path=norm_target,
                        metadata=metadata
                    )
                    node_map[action_key] = action_node_id
                    
                    if not self.nx_builder.graph.has_edge(page_node_id, action_node_id):
                        self.nx_builder.add_dependency(page_node_id, action_node_id, dep.type)
                return action_node_id
            return page_node_id
            
        elif dep.type == DependencyType.LOCATOR:
            node_key = (node_type, norm_target)
            if node_key in node_map:
                locator_node_id = node_map[node_key]
            else:
                locator_node_id = self.nx_builder.add_locator_node(norm_target, metadata)
                node_map[node_key] = locator_node_id
            return locator_node_id
            
        elif dep.type == DependencyType.DATABASE:
            node_key = (node_type, norm_target)
            if node_key in node_map:
                return node_map[node_key]
            
            node_id = self.nx_builder.add_database_node(norm_target, metadata)
            node_map[node_key] = node_id
            return node_id
        else:
            raise ValueError(f"Unknown dependency type: {dep.type}")

    def parse_api_hierarchy(self, endpoint: str) -> List[str]:
        """Parse API endpoint into segments."""
        if not endpoint or endpoint == '/':
            return []
            
        # Clean up endpoint
        endpoint_clean = endpoint.replace('http://', '').replace('https://', '')
        if endpoint_clean.startswith('localhost'):
            endpoint_clean = endpoint_clean[len('localhost'):].lstrip(':0123456789')
            
        if not endpoint_clean or endpoint_clean == '/':
            return []
            
        # Check if first part is domain or path
        domain = None
        path = endpoint_clean
        
        if endpoint_clean.startswith('/'):
            domain = None
            path = endpoint_clean
        else:
            if '/' in endpoint_clean:
                first_part = endpoint_clean.split('/')[0]
                if '.' in first_part or first_part.startswith('${'):
                    domain = first_part
                    path = '/' + '/'.join(endpoint_clean.split('/')[1:])
                else:
                    domain = None
                    path = endpoint_clean if endpoint_clean.startswith('/') else '/' + endpoint_clean
            else:
                domain = endpoint_clean if ('.' in endpoint_clean or endpoint_clean.startswith('${')) else None
                path = '' if domain else '/' + endpoint_clean
        
        segments = []
        if domain:
            segments.append(domain)
        if path:
            path_parts = [p for p in path.split('/') if p]
            segments.extend(path_parts)
        
        return segments

    def create_api_hierarchy(
        self,
        endpoint: str,
        metadata: NodeMetadata,
        node_map: Dict[Tuple, str]
    ) -> str:
        """Create hierarchical API structure and return leaf node ID."""
        http_method = metadata.additional_data.get("http_method", "GET")
        path_template = metadata.additional_data.get("path_template", "")
        examples = metadata.additional_data.get("examples", [])
        base_url = metadata.additional_data.get("base_url", "")
        
        if path_template and base_url:
            template_url = f"{base_url}{path_template}"
            segments = self.parse_api_hierarchy(template_url)
        else:
            segments = self.parse_api_hierarchy(endpoint)
        
        if not segments:
            return self.create_single_api_node(endpoint, metadata, node_map)
            
        static_segments = [seg for seg in segments if '{' not in seg]
        
        # Determine descriptive leaf name for metadata
        scenario_name = metadata.additional_data.get("scenario_name")
        scenario_tags = metadata.additional_data.get("scenario_tags", [])
        
        tag_str = ""
        if scenario_tags:
            first_tag = scenario_tags[0]
            tag_str = first_tag if first_tag.startswith("@") else f"@{first_tag}"
            
        descriptive_name = ""
        if scenario_name and scenario_name.strip():
            descriptive_name = f"{tag_str} - {scenario_name}" if tag_str else scenario_name
        elif tag_str:
            descriptive_name = tag_str
        
        # Use the normalized endpoint as the node name; method remains in metadata.
        display_name = endpoint
        if path_template and "{" in path_template:
            import re
            params = re.findall(r'\{([^}]+)\}', path_template)
            if params:
                display_name = f"{endpoint} {{{params[-1]}}}"
        
        # Add descriptive info to metadata
        if descriptive_name:
            metadata.additional_data["descriptive_name"] = descriptive_name
        
        parent_node_id = None
        for i, segment in enumerate(static_segments):
            cumulative_path = '/'.join(static_segments[:i+1])
            node_key = (NodeType.API_GROUP, cumulative_path)
            
            if node_key in node_map:
                current_node_id = node_map[node_key]
            else:
                group_display_name = base_url if (i == 0 and base_url) else segment
                group_metadata = NodeMetadata(
                    file_path=None,
                    line_number=None,
                    jira_tags=[],
                    project_name=metadata.project_name,
                    additional_data={
                        "level": i,
                        "segment": segment,
                        "base_url": base_url if i == 0 else None,
                        # cumulative_segment makes the hash unique across different domain trees
                        "cumulative_segment": cumulative_path,
                    },
                )
                current_node_id = self.nx_builder.add_api_group_node(group_display_name, group_metadata)
                node_map[node_key] = current_node_id

            
            if parent_node_id:
                if not self.nx_builder.graph.has_edge(parent_node_id, current_node_id):
                    self.nx_builder.add_dependency(parent_node_id, current_node_id, DependencyType.API)
            
            parent_node_id = current_node_id
        
        # API node key: use endpoint + http_method for dedup.
        # DYNAMIC method means we couldn't detect it statically — treat it as
        # the same node if another entry with the same URL already exists with
        # a concrete method (POST/GET/etc.), otherwise use DYNAMIC as key so
        # it can be enriched later.
        if http_method == "DYNAMIC":
            # Check if a concrete-method node already exists for this URL
            existing_key = next(
                (k for k in node_map if k[0] == NodeType.API and k[1].startswith(f"{endpoint}#") and not k[1].endswith("#DYNAMIC")),
                None
            )
            if existing_key:
                # Reuse the existing concrete-method node
                leaf_node_id = node_map[existing_key]
                if descriptive_name:
                    self.nx_builder.update_node_metadata(leaf_node_id, {
                        "descriptive_name": descriptive_name,
                        "scenario_name": scenario_name,
                        "scenario_tags": scenario_tags,
                    })
                if parent_node_id and not self.nx_builder.graph.has_edge(parent_node_id, leaf_node_id):
                    self.nx_builder.add_dependency(parent_node_id, leaf_node_id, DependencyType.API)
                return leaf_node_id

        node_key = (NodeType.API, f"{endpoint}#{http_method}")
        if node_key in node_map:
            leaf_node_id = node_map[node_key]
            # Update descriptive metadata if we found better info during definition scan
            if descriptive_name:
                self.nx_builder.update_node_metadata(leaf_node_id, {
                    "descriptive_name": descriptive_name,
                    "scenario_name": scenario_name,
                    "scenario_tags": scenario_tags
                })
        else:
            # Create new API node with HTTP Method as display name
            leaf_metadata = NodeMetadata(
                file_path=metadata.file_path,
                line_number=metadata.line_number,
                jira_tags=metadata.jira_tags,
                project_name=metadata.project_name,
                additional_data={
                    "full_url": endpoint,
                    "http_method": http_method,
                    "path_template": path_template,
                    "examples": metadata.additional_data.get("examples", []),
                    "level": metadata.additional_data.get("level", 0),
                    "descriptive_name": descriptive_name,
                    "scenario_name": scenario_name,
                    "scenario_tags": scenario_tags
                }
            )
            # Use display_name (Method) here, NOT the segment name
            leaf_node_id = self.nx_builder.add_api_node(display_name, leaf_metadata)
            node_map[node_key] = leaf_node_id
        
        if parent_node_id:
            if not self.nx_builder.graph.has_edge(parent_node_id, leaf_node_id):
                self.nx_builder.add_dependency(parent_node_id, leaf_node_id, DependencyType.API)
        
        return leaf_node_id

    def create_single_api_node(
        self,
        endpoint: str,
        metadata: NodeMetadata,
        node_map: Dict[Tuple, str]
    ) -> str:
        """Create a single API node without hierarchy."""
        node_key = (NodeType.API, endpoint)
        if node_key in node_map:
            return node_map[node_key]
        
        # Determine descriptive name
        scenario_name = metadata.additional_data.get("scenario_name")
        scenario_tags = metadata.additional_data.get("scenario_tags", [])
        
        tag_prefix = ""
        if scenario_tags:
            first_tag = scenario_tags[0]
            tag_prefix = first_tag if first_tag.startswith("@") else f"@{first_tag}"
            
        if scenario_name:
            display_name = f"{tag_prefix} - {scenario_name}" if tag_prefix else scenario_name
        else:
            display_name = endpoint

        node_id = self.nx_builder.add_api_node(display_name, metadata)
        node_map[node_key] = node_id
        return node_id
