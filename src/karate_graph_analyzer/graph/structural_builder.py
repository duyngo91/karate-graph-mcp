import os
import hashlib
import logging
from typing import Dict, List, Optional
from karate_graph_analyzer.models import NodeType, DependencyType, NodeMetadata, Project, ComponentCategory, FlowType
from karate_graph_analyzer.graph.core.nx_builder import NetworkXBuilder
from karate_graph_analyzer.utils.path_resolver import PathResolver
from karate_graph_analyzer.utils.scan_filters import is_excluded_path

logger = logging.getLogger(__name__)

class StructuralBuilder:
    """Builds the structural layer of the graph (folders and files)."""

    def __init__(self, nx_builder: NetworkXBuilder):
        self.nx_builder = nx_builder
        self.file_nodes: Dict[str, str] = {}  # Normalized path -> Node ID

    def build_structure(self, project: Project):
        """Scan project root and build folder/file hierarchy."""
        root_path = os.path.abspath(project.root_path)
        project_name = project.name
        
        # Mapping from folder path to its node ID to link parents to children
        folder_nodes: Dict[str, str] = {}
        
        # 1. Create root folder node
        root_metadata = NodeMetadata(
            file_path=root_path,
            line_number=None,
            jira_tags=[],
            project_name=project_name,
            category=ComponentCategory.INFRASTRUCTURE,
            flow=FlowType.INFRASTRUCTURE
        )
        root_id = self.nx_builder.add_folder_node(root_path, root_metadata)
        folder_nodes[root_path] = root_id

        # 2. Walk the directory tree
        exclude_dirs = {"__pycache__"}
        
        for root, dirs, files in os.walk(root_path):
            # Skip excluded directories
            dirs[:] = [
                d
                for d in dirs
                if d.lower() not in exclude_dirs
                and not is_excluded_path(os.path.join(root, d), project.parser_config)
            ]
            
            # Normalize root for lookup
            current_root = os.path.abspath(root)
            parent_folder_id = folder_nodes.get(current_root)
            if not parent_folder_id:
                logger.warning(f"Parent folder node not found for {current_root}")
                continue

            # Add subfolders
            for d in dirs:
                folder_path = os.path.abspath(os.path.join(current_root, d))
                metadata = NodeMetadata(
                    file_path=folder_path,
                    line_number=None,
                    jira_tags=[],
                    project_name=project_name,
                    category=ComponentCategory.INFRASTRUCTURE,
                    flow=FlowType.INFRASTRUCTURE
                )
                folder_id = self.nx_builder.add_folder_node(folder_path, metadata)
                folder_nodes[folder_path] = folder_id
                
                # Link parent to child
                self.nx_builder.add_dependency(parent_folder_id, folder_id, DependencyType.CONTAINS)

            # Add files
            for f in files:
                if not f.endswith((".feature", ".js", ".json", ".java")):
                    continue
                    
                file_path = os.path.abspath(os.path.join(current_root, f))
                # Use absolute path for structural identity, but store normalized path in metadata
                rel_path = PathResolver.normalize_path(file_path)
                
                metadata = NodeMetadata(
                    file_path=rel_path,
                    line_number=None,
                    jira_tags=[],
                    project_name=project_name,
                    category=ComponentCategory.BUSINESS if f.endswith(".feature") else ComponentCategory.INFRASTRUCTURE,
                    flow=FlowType.TEST if f.endswith(".feature") else FlowType.DATA
                )
                file_id = self.nx_builder.add_file_node(file_path, metadata)
                self.file_nodes[rel_path] = file_id
                
                # Link parent folder to file
                self.nx_builder.add_dependency(parent_folder_id, file_id, DependencyType.CONTAINS)

    def link_to_functional_node(self, file_path: str, functional_node_id: str):
        """Bridge the structural file node to a functional node defined within it."""
        rel_path = PathResolver.normalize_path(file_path)
        file_node_id = self.file_nodes.get(rel_path)
        if file_node_id:
            # FILE --CONTAINS--> FUNCTIONAL_COMPONENT
            # We use CONTAINS for the bridge as well to signify ownership
            self.nx_builder.add_dependency(file_node_id, functional_node_id, DependencyType.CONTAINS)
