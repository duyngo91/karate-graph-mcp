"""
Graph cache service with fingerprint validation.
"""

import glob
import hashlib
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from karate_graph_analyzer.exporters.json_exporter import JsonExporter
from karate_graph_analyzer.models import DependencyGraph, Project

logger = logging.getLogger(__name__)


class GraphCacheService:
    """Persist and load graph snapshots with freshness checks."""

    CACHE_VERSION = 2

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.exporter = JsonExporter()

    def load_if_fresh(
        self, project: Project, include_structural_nodes: bool
    ) -> Optional[DependencyGraph]:
        """Load a cached graph only when fingerprint matches current project state."""
        path = self.storage_dir / f"{project.name}.json"
        if not path.exists():
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except Exception as exc:
            logger.warning("Failed to parse graph cache '%s': %s", path, exc)
            return None

        # Backward compatibility: old cache stored raw graph JSON only.
        if not isinstance(payload, dict) or "graph" not in payload:
            try:
                return self.exporter.import_graph(raw, project.name)
            except Exception:
                return None

        expected_fingerprint = self._compute_fingerprint(project, include_structural_nodes)
        cached_fingerprint = payload.get("fingerprint")
        if cached_fingerprint != expected_fingerprint:
            return None

        graph_data = payload.get("graph")
        if not isinstance(graph_data, str):
            return None

        try:
            return self.exporter.import_graph(graph_data, project.name)
        except Exception:
            return None

    def save_project_graph(
        self, project: Project, graph: DependencyGraph, include_structural_nodes: bool
    ) -> bool:
        """Persist graph with fingerprint metadata."""
        try:
            payload = {
                "cache_version": self.CACHE_VERSION,
                "project_name": project.name,
                "fingerprint": self._compute_fingerprint(
                    project, include_structural_nodes
                ),
                "graph": self.exporter.export(graph),
            }
            path = self.storage_dir / f"{project.name}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return True
        except Exception as exc:
            logger.error("Failed to save graph cache for '%s': %s", project.name, exc)
            return False

    def save_raw_graph(self, project_name: str, graph: DependencyGraph) -> bool:
        """Persist raw graph JSON without fingerprint (for non-registered projects)."""
        try:
            path = self.storage_dir / f"{project_name}.json"
            path.write_text(self.exporter.export(graph), encoding="utf-8")
            return True
        except Exception as exc:
            logger.error("Failed to save raw graph cache for '%s': %s", project_name, exc)
            return False

    def _compute_fingerprint(
        self, project: Project, include_structural_nodes: bool
    ) -> str:
        file_entries = []
        for file_path in self._collect_feature_files(project):
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

    def _collect_feature_files(self, project: Project) -> list[str]:
        feature_files: list[str] = []
        for pattern in project.feature_file_patterns:
            full_pattern = str(Path(project.root_path) / pattern)
            matches = glob.glob(full_pattern, recursive=True)

            filtered_matches = []
            exclude_dirs = {"target", "build", "node_modules", ".git"}
            for match in matches:
                path_parts = [part.lower() for part in Path(match).parts]
                if not any(excluded in path_parts for excluded in exclude_dirs):
                    filtered_matches.append(match)

            feature_files.extend(filtered_matches)

        return sorted(set(feature_files))
