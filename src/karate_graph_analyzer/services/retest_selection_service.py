"""Change impact preview and smart test selection services."""

from typing import Any, Dict, List, Set

from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
from karate_graph_analyzer.models import DependencyGraph, Node


class RetestSelectionService:
    """Build change-impact previews and prioritized rerun test selections."""

    def __init__(self, graph: DependencyGraph, analyzer: DependencyAnalyzer) -> None:
        self.graph = graph
        self.analyzer = analyzer

    def change_impact_preview(
        self,
        changed_paths: List[str],
        limit: int = 50,
    ) -> Dict[str, Any]:
        matched_nodes = self.match_changed_nodes(changed_paths)
        impacted = self._collect_impacted_test_cases(matched_nodes)

        return {
            "matched_changed_nodes": [self._changed_node_payload(node) for node in matched_nodes],
            "impacted_test_cases": impacted[:limit],
            "count": min(len(impacted), limit),
            "total_available": len(impacted),
        }

    def test_selection_suggestion(
        self,
        changed_paths: List[str],
        limit: int = 30,
    ) -> Dict[str, Any]:
        preview = self.change_impact_preview(changed_paths, limit=500)
        selected = [
            self._selection_payload(item)
            for item in preview.get("impacted_test_cases", [])
        ]
        selected.sort(
            key=lambda x: (
                x.get("priority_score", 0),
                len(x.get("change_triggers", [])),
                x.get("name", ""),
            ),
            reverse=True,
        )

        return {
            "selection_strategy": "priority = trigger_count*10 - min_depth",
            "suggested_tests": selected[:limit],
            "count": min(len(selected), limit),
            "total_available": len(selected),
        }

    def match_changed_nodes(self, changed_paths: List[str]) -> List[Node]:
        """Resolve changed path patterns to graph nodes."""
        patterns = [
            path.strip().replace("\\", "/").lower()
            for path in changed_paths
            if path and path.strip()
        ]
        if not patterns:
            return []

        matched: List[Node] = []
        seen: Set[str] = set()
        for node in self.graph.nodes.values():
            file_path = (node.metadata.file_path or "").replace("\\", "/").lower()
            name = (node.name or "").replace("\\", "/").lower()
            if not self._matches_any_pattern([file_path, name], patterns):
                continue
            if node.id in seen:
                continue
            matched.append(node)
            seen.add(node.id)
        return matched

    def _collect_impacted_test_cases(self, matched_nodes: List[Node]) -> List[Dict[str, Any]]:
        impacted_map: Dict[str, Dict[str, Any]] = {}
        for changed in matched_nodes:
            impact = self.analyzer.impact_analysis(changed.id)
            for affected in impact.affected_test_cases:
                self._merge_affected_test_case(impacted_map, changed.name, affected)

        impacted = list(impacted_map.values())
        impacted.sort(
            key=lambda item: (
                -len(item.get("change_triggers", [])),
                item.get("min_depth", 9999),
                item.get("name", ""),
            )
        )
        return impacted

    def _merge_affected_test_case(
        self,
        impacted_map: Dict[str, Dict[str, Any]],
        changed_name: str,
        affected: Any,
    ) -> None:
        existing = impacted_map.get(affected.node_id)
        if not existing:
            impacted_map[affected.node_id] = {
                "node_id": affected.node_id,
                "name": affected.name,
                "jira_tags": affected.jira_tags,
                "min_depth": affected.depth,
                "change_triggers": [changed_name],
                "paths": [affected.dependency_path],
            }
            return

        existing["min_depth"] = min(existing.get("min_depth", affected.depth), affected.depth)
        if changed_name not in existing["change_triggers"]:
            existing["change_triggers"].append(changed_name)
        if affected.dependency_path not in existing["paths"]:
            existing["paths"].append(affected.dependency_path)

    def _selection_payload(self, impacted_case: Dict[str, Any]) -> Dict[str, Any]:
        trigger_count = len(impacted_case.get("change_triggers", []))
        min_depth = impacted_case.get("min_depth", 0)
        return {
            "node_id": impacted_case.get("node_id"),
            "name": impacted_case.get("name"),
            "jira_tags": impacted_case.get("jira_tags", []),
            "priority_score": (trigger_count * 10) - min_depth,
            "reason": f"triggered_by={trigger_count}, min_depth={min_depth}",
            "change_triggers": impacted_case.get("change_triggers", []),
        }

    def _changed_node_payload(self, node: Node) -> Dict[str, Any]:
        return {
            "id": node.id,
            "type": node.type.value,
            "name": node.name,
            "file_path": node.metadata.file_path,
        }

    def _matches_any_pattern(self, values: List[str], patterns: List[str]) -> bool:
        return any(pattern in value for pattern in patterns for value in values if value)
