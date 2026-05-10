"""Project fingerprinting for graph cache freshness."""

import glob
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from karate_graph_analyzer.models import Project
from karate_graph_analyzer.utils.scan_filters import is_excluded_path


class FingerprintService:
    """Compute graph cache fingerprints from project inputs."""

    def compute_project_fingerprint(
        self, project: Project, include_structural_nodes: bool
    ) -> str:
        file_entries = []
        for file_path in self.collect_project_files(project):
            path_obj = Path(file_path)
            try:
                stat = path_obj.stat()
            except OSError:
                continue
            file_entries.append(
                {
                    "path": str(path_obj.resolve()).lower(),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )

        parser_config = asdict(project.parser_config) if project.parser_config else {}
        fingerprint_source: Dict[str, Any] = {
            "project_name": project.name,
            "root_path": str(Path(project.root_path).resolve()).lower(),
            "feature_file_patterns": project.feature_file_patterns,
            "parser_config": parser_config,
            "include_structural_nodes": include_structural_nodes,
            "files": sorted(file_entries, key=lambda item: item["path"]),
        }
        encoded = json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def collect_project_files(self, project: Project) -> list[str]:
        """Collect graph inputs that should invalidate the cached project graph."""
        feature_files: list[str] = []
        for pattern in project.feature_file_patterns:
            full_pattern = str(Path(project.root_path) / pattern)
            for match in glob.iglob(full_pattern, recursive=True):
                if not is_excluded_path(match, project.parser_config):
                    feature_files.append(match)

        for pattern in getattr(project.parser_config, "javascript_file_patterns", ["**/*.js"]):
            js_pattern = str(Path(project.root_path) / pattern)
            for match in glob.iglob(js_pattern, recursive=True):
                if not is_excluded_path(match, project.parser_config):
                    feature_files.append(match)

        return sorted(set(feature_files))

    def collect_feature_files(self, project: Project) -> list[str]:
        """Backward-compatible name for callers that need graph input files."""
        return self.collect_project_files(project)
