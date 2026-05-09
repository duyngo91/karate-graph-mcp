"""Prioritize failure fixes from hotspots and execution history."""

from typing import Any, Dict, List

from karate_graph_analyzer.models import DependencyGraph
from karate_graph_analyzer.services.failure_context_service import FailureContextService


class FixPriorityService:
    """Rank components or tests by blast radius, failure rate, and flakiness."""

    SCORING = {
        "formula": "priority = impact*10 + failure_rate*100 + flaky_score*20",
        "weights": {"impact": 10, "failure_rate": 100, "flaky_score": 20},
    }

    def __init__(
        self,
        graph: DependencyGraph,
        failure_context_service: FailureContextService,
    ) -> None:
        self.graph = graph
        self.failure_context_service = failure_context_service

    def prioritize(self, hotspots: List[Dict[str, Any]], limit: int = 10) -> Dict[str, Any]:
        impacted_by_node = self._build_hotspot_index(hotspots)
        ranked = [
            ranked_item
            for node_id, hotspot_info in impacted_by_node.items()
            if (ranked_item := self._ranked_item(node_id, hotspot_info)) is not None
        ]
        ranked.sort(
            key=lambda item: (
                item["priority_score"],
                item["impact_score"],
                item["failure_rate"],
                item["fail_count"],
            ),
            reverse=True,
        )

        return {
            "results": ranked[:limit],
            "count": min(len(ranked), limit),
            "total_available": len(ranked),
            "scoring": self.SCORING,
        }

    def _build_hotspot_index(self, hotspots: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        impacted_by_node: Dict[str, Dict[str, Any]] = {}
        for hotspot in hotspots:
            self._index_hotspot_node(impacted_by_node, hotspot)
            for test_case in hotspot.get("affected_failed_test_cases", []):
                self._index_affected_test_case(impacted_by_node, hotspot, test_case)
        return impacted_by_node

    def _index_hotspot_node(
        self,
        impacted_by_node: Dict[str, Dict[str, Any]],
        hotspot: Dict[str, Any],
    ) -> None:
        hotspot_node_id = hotspot.get("node_id")
        if not hotspot_node_id:
            return
        impacted_by_node[hotspot_node_id] = self._hotspot_payload(hotspot)

    def _index_affected_test_case(
        self,
        impacted_by_node: Dict[str, Dict[str, Any]],
        hotspot: Dict[str, Any],
        test_case: Dict[str, Any],
    ) -> None:
        test_case_id = test_case.get("node_id") or test_case.get("id")
        if not test_case_id:
            return
        candidate = self._hotspot_payload(hotspot)
        existing = impacted_by_node.get(test_case_id)
        if not existing or candidate["score"] > existing["score"]:
            impacted_by_node[test_case_id] = candidate

    def _hotspot_payload(self, hotspot: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "score": hotspot.get("failure_impact_score", 0),
            "failure_rate": hotspot.get("failure_percentage", 0),
            "hotspot_name": hotspot.get("name"),
            "hotspot_type": hotspot.get("type"),
        }

    def _ranked_item(
        self,
        node_id: str,
        hotspot_info: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        node = self.graph.nodes.get(node_id)
        if not node:
            return None

        history = self.failure_context_service.build_history_payload(node)
        fail_count = history.get("fail_count", 0)
        total_runs = history.get("total_runs", 0)
        failure_rate = history.get("failure_rate", 0.0)
        flaky_score = history.get("flaky_score", 0.0)
        impact_score = hotspot_info.get("score", 0)
        priority_score = (impact_score * 10.0) + (failure_rate * 100.0) + (flaky_score * 20.0)

        return {
            "node_id": node.id,
            "name": node.name,
            "type": node.type.value,
            "status": node.execution_status,
            "file_path": node.metadata.file_path,
            "line_number": node.metadata.line_number,
            "priority_score": round(priority_score, 3),
            "impact_score": impact_score,
            "failure_rate": failure_rate,
            "fail_count": fail_count,
            "total_runs": total_runs,
            "flaky_score": flaky_score,
            "failure_category": node.metadata.additional_data.get("failure_category"),
            "top_fingerprint": self._top_fingerprint(history),
            "linked_hotspot": {
                "name": hotspot_info.get("hotspot_name"),
                "type": hotspot_info.get("hotspot_type"),
                "failure_rate": hotspot_info.get("failure_rate"),
            },
            "why_now": self._why_now(impact_score, failure_rate, total_runs, flaky_score),
        }

    def _why_now(
        self,
        impact_score: float,
        failure_rate: float,
        total_runs: int,
        flaky_score: float,
    ) -> str:
        reason_parts = [
            f"impact={impact_score}",
            f"failure_rate={round(failure_rate * 100, 1)}%",
        ]
        if total_runs > 1:
            reason_parts.append(f"runs={total_runs}")
        if flaky_score > 0:
            reason_parts.append(f"flaky={round(flaky_score, 3)}")
        return ", ".join(reason_parts)

    def _top_fingerprint(self, history: Dict[str, Any]) -> str | None:
        fingerprints = history.get("failure_fingerprints") or []
        return fingerprints[0]["fingerprint"] if fingerprints else None
