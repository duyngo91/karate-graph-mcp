"""
Project registry implementation.

Manages registration and persistence of Karate projects.
Implements IProjectRepository (Repository Pattern) for storage abstraction.
"""

import glob
import json
import os
import tempfile
from dataclasses import asdict
from typing import List, Optional

from karate_graph_analyzer.interfaces import IProjectRepository
from karate_graph_analyzer.models import ParserConfig, Project


class ProjectRegistry(IProjectRepository):
    """JSON-file backed project repository.

    Implements IProjectRepository for managing multiple Karate projects
    using a local JSON file as persistent storage.

    Can be replaced with SQLite, Neo4j, or other storage backends
    by implementing IProjectRepository interface.
    """

    def __init__(self, storage_path: str = ".karate_projects.json") -> None:
        """Initialize project registry.

        Args:
            storage_path: Path to the registry storage file
        """
        self.storage_path = storage_path
        self.projects: dict[str, Project] = {}

    def add(self, project: Project) -> None:
        """Add a project to the registry.

        Args:
            project: Project to add

        Raises:
            ValueError: If project with same name already exists or validation fails
        """
        # Check if project with same name already exists
        if project.name in self.projects:
            raise ValueError(
                f"Project with name '{project.name}' already exists in registry"
            )

        # Validate project path exists
        if not os.path.exists(project.root_path):
            raise ValueError(
                f"Project root path does not exist: {project.root_path}"
            )

        # Validate that project contains at least one feature file
        feature_files = self._find_feature_files(project)
        if not feature_files:
            raise ValueError(
                f"No feature files found in project '{project.name}' at path "
                f"{project.root_path} matching patterns {project.feature_file_patterns}"
            )

        # Add project to registry
        self.projects[project.name] = project

    def remove(self, project_name: str) -> None:
        """Remove a project from the registry.

        Args:
            project_name: Name of the project to remove

        Raises:
            KeyError: If project does not exist
        """
        if project_name not in self.projects:
            raise KeyError(f"Project '{project_name}' not found in registry")

        del self.projects[project_name]

    def get(self, project_name: str) -> Optional[Project]:
        """Get a project by name.

        Args:
            project_name: Name of the project

        Returns:
            Project if found, None otherwise
        """
        return self.projects.get(project_name)

    def list(self) -> List[Project]:
        """List all registered projects.

        Returns:
            List of all projects
        """
        return list(self.projects.values())

    def save(self) -> None:
        """Persist registry to disk using atomic writes.
        
        Uses atomic write pattern (write to temp file, then rename) to prevent
        corruption during save operations.
        
        Raises:
            IOError: If unable to write to storage file
        """
        # Serialize all projects to dictionaries
        projects_data = []
        for project in self.projects.values():
            project_dict = asdict(project)
            projects_data.append(project_dict)
        
        # Create JSON data structure
        registry_data = {
            "version": "1.0",
            "projects": projects_data
        }
        
        # Write to temporary file first (atomic write pattern)
        storage_dir = os.path.dirname(self.storage_path) or "."
        
        # Ensure directory exists
        if storage_dir != ".":
            os.makedirs(storage_dir, exist_ok=True)
        
        # Create temp file in same directory as target file
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=storage_dir,
            delete=False,
            suffix='.tmp'
        ) as temp_file:
            json.dump(registry_data, temp_file, indent=2)
            temp_file_path = temp_file.name
        
        try:
            # Atomic rename (replaces existing file)
            os.replace(temp_file_path, self.storage_path)
        except Exception:
            # Clean up temp file if rename fails
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise

    def load(self) -> None:
        """Load registry from disk.
        
        Handles missing files gracefully (empty registry) and validates loaded data.
        
        Raises:
            ValueError: If registry file is corrupted or invalid
        """
        # If file doesn't exist, start with empty registry
        if not os.path.exists(self.storage_path):
            self.projects = {}
            return
        
        try:
            # Read JSON file
            with open(self.storage_path, 'r') as f:
                registry_data = json.load(f)
            
            # Validate structure
            if not isinstance(registry_data, dict):
                raise ValueError("Registry file has invalid structure: expected dict")
            
            if "projects" not in registry_data:
                raise ValueError("Registry file missing 'projects' key")
            
            if not isinstance(registry_data["projects"], list):
                raise ValueError("Registry 'projects' must be a list")
            
            # Deserialize projects
            self.projects = {}
            for project_dict in registry_data["projects"]:
                # Reconstruct ParserConfig if present
                if "parser_config" in project_dict and project_dict["parser_config"]:
                    parser_config_dict = project_dict["parser_config"]
                    parser_config = ParserConfig(**parser_config_dict)
                    project_dict["parser_config"] = parser_config
                
                # Reconstruct Project
                project = Project(**project_dict)
                self.projects[project.name] = project
                
        except json.JSONDecodeError as e:
            raise ValueError(f"Registry file is corrupted: invalid JSON - {e}")
        except (KeyError, TypeError) as e:
            raise ValueError(f"Registry file has invalid structure: {e}")

    def _find_feature_files(self, project: Project) -> List[str]:
        """Find all feature files in project matching patterns.

        Args:
            project: Project to scan for feature files

        Returns:
            List of feature file paths
        """
        feature_files = []
        for pattern in project.feature_file_patterns:
            # Construct full path pattern
            full_pattern = os.path.join(project.root_path, pattern)
            # Use glob to find matching files
            matches = glob.glob(full_pattern, recursive=True)
            feature_files.extend(matches)

        # Remove duplicates and return
        return list(set(feature_files))

    def list_all(self) -> List[Project]:
        """List all registered projects (IProjectRepository interface).

        Returns:
            List of all projects
        """
        return self.list_projects()

    def remove(self, project_name: str) -> None:
        """Remove a project from the registry (IProjectRepository interface).

        Args:
            project_name: Name of the project to remove

        Raises:
            KeyError: If project does not exist
        """
        if project_name not in self.projects:
            raise KeyError(f"Project '{project_name}' not found")
        del self.projects[project_name]
        self.save()


# Backward-compatible alias
JsonProjectRepository = ProjectRegistry
