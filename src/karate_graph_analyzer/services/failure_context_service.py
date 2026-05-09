"""Build compact failure context packs for AI-assisted debugging."""

from collections import Counter
from typing import Any, Dict, List, Optional

from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
from karate_graph_analyzer.models import DependencyGraph, Node, NodeType
from karate_graph_analyzer.utils.failure_signature import (
    build_failure_fingerprint,
    classify_failure,
    extract_http_status_signal,
)
from karate_graph_analyzer.utils.source_snippet import get_source_snippet


class FailureContextService:
    """Creates AI-friendly failure and history payloads from the graph."""

    def resolve_error_message(self, node: Node, override: Optional[str] = None) -> str:
        if override:
            return override

        details = node.execution_details or {}
        additional = node.metadata.additional_data or {}
        display = additional.get("display_data", {})
        return (
            details.get("error")
            or additional.get("last_error")
            or display.get("details", {}).get("last_error")
            or ""
        )

    def build_failure_payload(self, node: Node, error_message: Optional[str] = None) -> Dict[str, Any]:
        error = self.resolve_error_message(node, error_message)
        failed_step = node.execution_details.get("failed_step")
        fingerprint = (
            node.execution_details.get("failure_fingerprint")
            or node.metadata.additional_data.get("failure_fingerprint")
            or build_failure_fingerprint(error, failed_step)
        )
        category = (
            node.execution_details.get("failure_category")
            or node.metadata.additional_data.get("failure_category")
            or classify_failure(error, failed_step)
        )

        return {
            "status": node.execution_status,
            "error_message": error,
            "failed_step": failed_step,
            "fingerprint": fingerprint,
            "category": category,
            "http_status": node.execution_details.get("http_status") or extract_http_status_signal(error),
            "run_context": node.execution_details.get("run_context") or node.metadata.additional_data.get("last_run", {}).get("run_context"),
            "artifacts": node.execution_details.get("artifacts") or node.metadata.additional_data.get("last_artifacts", []),
        }

    def build_history_payload(self, node: Node) -> Dict[str, Any]:
        runs = list(node.metadata.additional_data.get("execution_runs", []))
        statuses = [run.get("status") for run in runs if run.get("status")]
        if not statuses:
            statuses = list(node.metadata.execution_history or [])

        pass_count = sum(1 for status in statuses if status == "PASSED")
        fail_count = sum(1 for status in statuses if status == "FAILED")
        total_runs = pass_count + fail_count
        failure_rate = fail_count / total_runs if total_runs else 0.0
        flaky_score = min(pass_count, fail_count) / total_runs if total_runs and pass_count and fail_count else 0.0
        failures = [run for run in runs if run.get("status") == "FAILED"]
        fingerprint_counts = Counter(
            run.get("failure_fingerprint") or "UNKNOWN"
            for run in failures
        )

        return {
            "total_runs": total_runs,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "failure_rate": round(failure_rate, 4),
            "flaky_score": round(flaky_score, 4),
            "last_status": node.execution_status,
            "recent_statuses": statuses[-10:],
            "first_failed_run": failures[0] if failures else None,
            "last_failed_run": failures[-1] if failures else None,
            "failure_fingerprints": [
                {"fingerprint": fingerprint, "count": count}
                for fingerprint, count in fingerprint_counts.most_common()
            ],
            "runs": runs[-20:],
        }

    def build_node_payload(self, node: Node) -> Dict[str, Any]:
        return {
            "id": node.id,
            "name": node.name,
            "type": node.type.value,
            "file_path": node.metadata.file_path,
            "line_number": node.metadata.line_number,
            "jira_tags": node.metadata.jira_tags,
            "tags": node.tags,
            "scenario_tag": node.metadata.additional_data.get("scenario_tag"),
            "action_tag": node.metadata.additional_data.get("action_tag"),
            "source_snippet": get_source_snippet(node.metadata.file_path, node.metadata.line_number),
        }

    def build_related_hotspots(
        self,
        analyzer: DependencyAnalyzer,
        node_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        related = []
        for hotspot in analyzer.find_failure_hotspots():
            affected_ids = {
                item.get("node_id") or item.get("id")
                for item in hotspot.get("affected_failed_test_cases", [])
            }
            if hotspot.get("node_id") == node_id or node_id in affected_ids:
                related.append(hotspot)
        return related[:limit]

    def build_dependency_context(
        self,
        analyzer: DependencyAnalyzer,
        node_id: str,
        radius: int,
    ) -> Dict[str, Any]:
        subgraph = analyzer.get_subgraph(node_id, radius=radius)
        nodes = subgraph.get("nodes", [])
        edges = subgraph.get("edges", [])

        return {
            "radius": radius,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }

    def build_debug_context(
        self,
        graph: DependencyGraph,
        analyzer: DependencyAnalyzer,
        node_id: str,
        error_message: Optional[str] = None,
        radius: int = 2,
    ) -> Dict[str, Any]:
        node = graph.nodes[node_id]
        failure = self.build_failure_payload(node, error_message)
        history = self.build_history_payload(node)

        return {
            "node": self.build_node_payload(node),
            "failure": failure,
            "history": history,
            "dependency_context": self.build_dependency_context(analyzer, node_id, radius),
            "related_hotspots": self.build_related_hotspots(analyzer, node_id),
            "ai_routing": self.build_ai_routing(failure, node),
        }

    def build_ai_routing(self, failure: Dict[str, Any], node: Node) -> Dict[str, Any]:
        category = failure.get("category") or "UNKNOWN"
        suggested_owner = "test"
        if category.startswith("HTTP_5XX"):
            suggested_owner = "backend"
        elif category in {"HTTP_401_AUTH", "HTTP_403_AUTHZ"}:
            suggested_owner = "auth/platform"
        elif category == "TIMEOUT":
            suggested_owner = "environment/backend"
        elif node.type in {NodeType.PAGE, NodeType.ACTION, NodeType.LOCATOR}:
            suggested_owner = "ui-automation"
        elif node.type in {NodeType.JAVASCRIPT, NodeType.JS_FUNCTION}:
            suggested_owner = "test-framework/javascript"

        next_steps = [
            "Open the source snippet and confirm the failing step maps to the current node.",
            "Inspect the dependency context for the nearest shared component or API hotspot.",
            "Compare this fingerprint with historical runs before changing test code.",
        ]
        if category.startswith("HTTP_"):
            next_steps.insert(1, "Check the API method/path/status signal and backend correlation logs.")
        if category == "TIMEOUT":
            next_steps.insert(1, "Check environment latency, downstream service health, and retry behavior.")
        if node.type in {NodeType.JAVASCRIPT, NodeType.JS_FUNCTION}:
            next_steps.insert(1, "Inspect JS helper/config inputs, exported function shape, and call/read dependencies.")

        return {
            "suggested_owner": suggested_owner,
            "next_steps": next_steps,
        }
