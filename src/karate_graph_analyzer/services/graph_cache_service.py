"""
Graph cache service with fingerprint validation.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from karate_graph_analyzer.exporters.json_exporter import JsonExporter
from karate_graph_analyzer.models import DependencyGraph, Project
from karate_graph_analyzer.services.fingerprint_service import FingerprintService

logger = logging.getLogger(__name__)


class GraphCacheService:
    """Persist and load graph snapshots with freshness checks."""

    CACHE_VERSION = 3

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.exporter = JsonExporter()
        self.fingerprint_service = FingerprintService()
        self._last_fingerprints: dict[tuple[str, bool], str] = {}

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
            return None

        if payload.get("cache_version") != self.CACHE_VERSION:
            return None

        expected_fingerprint = self._compute_project_fingerprint(
            project,
            include_structural_nodes,
        )
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
                "fingerprint": self._get_cached_or_compute_fingerprint(project, include_structural_nodes),
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

    def _compute_project_fingerprint(
        self,
        project: Project,
        include_structural_nodes: bool,
    ) -> str:
        fingerprint = self.fingerprint_service.compute_project_fingerprint(
            project,
            include_structural_nodes,
        )
        self._last_fingerprints[(project.name, include_structural_nodes)] = fingerprint
        return fingerprint

    def _get_cached_or_compute_fingerprint(
        self,
        project: Project,
        include_structural_nodes: bool,
    ) -> str:
        key = (project.name, include_structural_nodes)
        return self._last_fingerprints.get(key) or self._compute_project_fingerprint(
            project,
            include_structural_nodes,
        )
