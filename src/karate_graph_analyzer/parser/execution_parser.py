import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from karate_graph_analyzer.models import DependencyGraph, NodeType, DependencyType
from karate_graph_analyzer.utils.failure_signature import (
    build_failure_fingerprint,
    classify_failure,
    extract_http_status_signal,
)

logger = logging.getLogger(__name__)

class ExecutionReportParser:
    """Parses Karate execution reports and maps results to graph nodes."""

    def __init__(self, graph: DependencyGraph, run_context: Optional[Dict[str, Any]] = None):
        self.graph = graph
        self.run_context = run_context or self._default_run_context()

    def _default_run_context(self) -> Dict[str, Any]:
        applied_at = datetime.now(timezone.utc).isoformat()
        return {
            "run_id": f"manual:{applied_at}",
            "applied_at": applied_at,
        }

    def _merge_run_context(self, run_context: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._default_run_context()
        merged.update(run_context)
        if not merged.get("run_id"):
            merged["run_id"] = f"manual:{merged['applied_at']}"
        return merged

    def _report_run_context(self, report_path: Path) -> Dict[str, Any]:
        resolved = report_path.resolve()
        stat = report_path.stat()
        applied_at = datetime.now(timezone.utc).isoformat()
        return {
            "run_id": f"{report_path.stem}:{stat.st_mtime_ns}",
            "report_path": str(resolved),
            "report_file": report_path.name,
            "report_mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "applied_at": applied_at,
        }

    def apply_report_data(self, data: Any, run_context: Optional[Dict[str, Any]] = None) -> int:
        """Apply already loaded report data to the graph nodes."""
        if run_context:
            self.run_context = self._merge_run_context(run_context)

        features = data if isinstance(data, list) else [data]
        applied_count = 0
        
        for feature in features:
            if self._process_feature(feature):
                applied_count += 1
        
        # Identify all leaf nodes that have status and trigger propagation
        if applied_count > 0:
            for node_id, node in self.graph.nodes.items():
                if node.type in [NodeType.TEST_CASE, NodeType.SCENARIO] and node.execution_status:
                    self._propagate_status_to_parents(node_id)
                    
        return applied_count

    def scan_directory(self, directory_path: str) -> List[str]:
        """Scan directory for Cucumber JSON report files."""
        dir_path = Path(directory_path)
        if not dir_path.exists() or not dir_path.is_dir():
            logger.error(f"Invalid directory path: {directory_path}")
            return []
            
        # Standard Karate Cucumber JSON files are usually named like: src.test.java...json
        # We want to exclude karate-summary.json and other metadata files
        json_files = []
        for p in dir_path.glob("*.json"):
            if p.name == "karate-summary.json":
                continue
            # Basic heuristic: Karate JSONs usually contain an array of features
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    content = f.read(100)
                    if content.strip().startswith('['):
                        json_files.append(str(p))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
                
        return json_files

    def get_ai_summary(self) -> Dict[str, Any]:
        """Generate a distilled summary of execution results for AI consumption."""
        summary = {
            "total_nodes": len(self.graph.nodes),
            "failed_components": [],
            "status_overview": {}
        }
        
        for node_id, node in self.graph.nodes.items():
            status = node.execution_status
            if not status: continue
            
            summary["status_overview"][status] = summary["status_overview"].get(status, 0) + 1
            
            if status in ["FAILED", "PARTIAL_FAIL"]:
                comp_info = {
                    "id": node_id,
                    "name": node.name,
                    "type": node.type.value,
                    "path": node.metadata.file_path
                }
                
                # Add error details for leaf nodes
                if node.type in [NodeType.TEST_CASE, NodeType.SCENARIO]:
                    comp_info["error"] = (node.execution_details or {}).get("error") or \
                                       node.metadata.additional_data.get("last_error")
                    comp_info["details"] = node.execution_details
                    
                summary["failed_components"].append(comp_info)
                
        return summary

    def apply_reports(self, report_paths: List[str]) -> int:
        """Load and apply multiple report files to the graph nodes."""
        total_applied = 0
        
        for path in report_paths:
            try:
                # Track which nodes were updated in this report
                # (We need to modify _apply_single_report to return them or just collect them)
                if self._apply_single_report(path):
                    total_applied += 1
            except Exception as e:
                logger.error(f"Failed to apply report {path}: {str(e)}")
        
        # Identify all leaf nodes that have status and trigger propagation
        for node_id, node in self.graph.nodes.items():
            if node.type in [NodeType.TEST_CASE, NodeType.SCENARIO] and node.execution_status:
                self._propagate_status_to_parents(node_id)
                
        return total_applied

    def _apply_single_report(self, report_path: str) -> bool:
        """Parses a single Karate JSON report and updates matching nodes."""
        path = Path(report_path)
        if not path.exists():
            logger.warning(f"Report file not found: {report_path}")
            return False

        self.run_context = self._report_run_context(path)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Karate reports can be a single feature dict or a list of features
        features = data if isinstance(data, list) else [data]
        
        applied = False
        for feature in features:
            if self._process_feature(feature):
                applied = True
        return applied

    def _process_feature(self, feature: Dict[str, Any]) -> bool:
        """Processes a feature object from Karate JSON report."""
        feature_uri = feature.get("uri") or feature.get("relativePath") or feature.get("prefixedPath") or ""
        applied = False

        for scenario_data in self._extract_scenarios(feature):
            scenario_name = self._get_scenario_name(scenario_data)
            if not scenario_name:
                continue

            status = self._detect_scenario_status(scenario_data)
            matched = False
            for node in self.graph.nodes.values():
                if not self._node_matches_scenario(node, scenario_name, feature_uri):
                    continue

                details = self._extract_failure_details(scenario_data) if status == "FAILED" else None
                execution_record = self._build_execution_record(
                    status,
                    scenario_data,
                    feature_uri,
                    details,
                )
                if details:
                    node.metadata.additional_data["last_error"] = details["error"]

                self._update_node_status(node.id, status, details, execution_record)
                matched = True
                applied = True
            
            if not matched:
                logger.debug(f"Could not map scenario '{scenario_name}' in '{feature_uri}' to any graph node")
                
        return applied

    def _extract_scenarios(self, feature: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle the common Karate/Cucumber report shapes."""
        return (
            feature.get("elements", [])
            or feature.get("scenarios", [])
            or feature.get("scenarioResults", [])
        )

    def _get_scenario_name(self, scenario_data: Dict[str, Any]) -> Optional[str]:
        if scenario_data.get("name") or scenario_data.get("executorName"):
            return scenario_data.get("name") or scenario_data.get("executorName")
        if scenario_data.get("type") == "scenario":
            return scenario_data.get("name")
        return None

    def _detect_scenario_status(self, scenario_data: Dict[str, Any]) -> str:
        """Detect status across standard Cucumber JSON and Karate JSON variants."""
        if "failed" in scenario_data:
            passed = not scenario_data.get("failed")
        elif "passed" in scenario_data:
            passed = scenario_data.get("passed")
        elif "status" in scenario_data:
            passed = scenario_data.get("status") == "passed"
        elif "result" in scenario_data:
            passed = scenario_data.get("result", {}).get("status") == "passed"
        else:
            passed = self._all_steps_passed(scenario_data)

        return "PASSED" if passed else "FAILED"

    def _all_steps_passed(self, scenario_data: Dict[str, Any]) -> bool:
        for step in scenario_data.get("steps", []):
            result = step.get("result", {})
            if result.get("status") == "failed":
                error_msg = result.get("error_message")
                if error_msg:
                    scenario_data["error"] = error_msg
                return False
        return True

    def _extract_failure_details(self, scenario_data: Dict[str, Any]) -> Dict[str, Optional[str]]:
        error_msg = scenario_data.get("error") or scenario_data.get("error_message") or "Unknown error"
        failed_step = self._find_failed_step(scenario_data)
        return {
            "error": error_msg,
            "failed_step": failed_step,
            "failure_fingerprint": build_failure_fingerprint(error_msg, failed_step),
            "failure_category": classify_failure(error_msg, failed_step),
            "http_status": extract_http_status_signal(error_msg),
            "artifacts": self._extract_artifacts(scenario_data),
            "run_context": self.run_context,
        }

    def _build_execution_record(
        self,
        status: str,
        scenario_data: Dict[str, Any],
        feature_uri: str,
        details: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        error = (details or {}).get("error")
        failed_step = (details or {}).get("failed_step")
        return {
            "run_id": self.run_context.get("run_id"),
            "status": status,
            "feature_uri": feature_uri,
            "scenario_name": self._get_scenario_name(scenario_data),
            "duration_ms": self._extract_duration_ms(scenario_data),
            "error": error,
            "failed_step": failed_step,
            "failure_fingerprint": (details or {}).get("failure_fingerprint"),
            "failure_category": (details or {}).get("failure_category"),
            "http_status": (details or {}).get("http_status"),
            "artifacts": (details or {}).get("artifacts", []),
            "run_context": self.run_context,
        }

    def _extract_duration_ms(self, scenario_data: Dict[str, Any]) -> Optional[float]:
        for key in ("duration", "duration_ms", "durationMillis"):
            if scenario_data.get(key) is not None:
                return scenario_data.get(key)

        total = 0
        found = False
        for step in scenario_data.get("steps", []):
            result = step.get("result", {})
            duration = result.get("duration") or result.get("duration_ms") or result.get("durationMillis")
            if duration is not None:
                found = True
                total += duration
        return total if found else None

    def _extract_artifacts(self, scenario_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        artifacts: List[Dict[str, Any]] = []

        def collect(container: Dict[str, Any], scope: str):
            for key in ("embeddings", "attachments", "artifacts", "output"):
                raw_items = container.get(key)
                if not raw_items:
                    continue
                items = raw_items if isinstance(raw_items, list) else [raw_items]
                for item in items:
                    artifacts.append(self._artifact_summary(item, scope, key))

        collect(scenario_data, "scenario")
        for index, step in enumerate(scenario_data.get("steps", []), start=1):
            collect(step, f"step:{index}")
            result = step.get("result", {})
            if isinstance(result, dict):
                collect(result, f"step:{index}:result")

        return artifacts

    def _artifact_summary(self, item: Any, scope: str, source_key: str) -> Dict[str, Any]:
        if isinstance(item, dict):
            data = item.get("data")
            text = item.get("text") or item.get("content")
            return {
                "scope": scope,
                "source": source_key,
                "name": item.get("name") or item.get("fileName") or item.get("filename"),
                "mime_type": item.get("mime_type") or item.get("mimeType") or item.get("mediaType"),
                "path": item.get("path") or item.get("file") or item.get("url"),
                "size": len(data) if isinstance(data, str) else item.get("size"),
                "preview": str(text or data or "")[:300] if (text or data) else None,
            }

        return {
            "scope": scope,
            "source": source_key,
            "preview": str(item)[:300],
        }

    def _node_matches_scenario(self, node, scenario_name: str, feature_uri: str) -> bool:
        if node.type not in [NodeType.SCENARIO, NodeType.TEST_CASE]:
            return False

        node_name = self._normalize_scenario_name(node.name)
        report_name = scenario_name.lower()
        name_match = (
            report_name == node_name
            or report_name in node_name
            or node_name in report_name
        )

        logger.debug(
            f"Comparing scenario '{report_name}' with node '{node_name}' "
            f"(type: {node.type}): match={name_match}"
        )
        if not name_match:
            return False

        return self._uri_matches(feature_uri, node.metadata.file_path or "")

    def _normalize_scenario_name(self, name: str) -> str:
        return re.sub(r'^\[[^\]]+\]\s*', '', name.lower()).lower()

    def _uri_matches(self, feature_uri: str, node_file: str) -> bool:
        if not feature_uri:
            return True

        norm_uri = feature_uri.replace("\\", "/")
        norm_node_file = node_file.replace("\\", "/")
        uri_match = (norm_uri in norm_node_file) or (norm_node_file in norm_uri)

        logger.debug(f"Comparing URI '{norm_uri}' with node file '{norm_node_file}': match={uri_match}")
        return uri_match or not (norm_uri and norm_node_file)

    def _find_failed_step(self, scenario_data: Dict[str, Any]) -> Optional[str]:
        """Extract the name of the step that failed."""
        steps = scenario_data.get("steps", [])
        for step in steps:
            result = step.get("result", {})
            if result.get("status") == "failed":
                return f"{step.get('keyword', '')} {step.get('name', '')}"
        return None

    def _update_node_status(
        self,
        node_id: str,
        status: str,
        details: Optional[Dict] = None,
        execution_record: Optional[Dict[str, Any]] = None,
    ):
        """Update current status, append to execution history, and maintain counts."""
        node = self.graph.nodes.get(node_id)
        if not node:
            return
            
        node.execution_status = status
        
        # Initialize counts for leaf nodes
        if node.type in [NodeType.TEST_CASE, NodeType.SCENARIO]:
            if not node.execution_details:
                node.execution_details = {}
            node.execution_details["failed_count"] = 1 if status == "FAILED" else 0
            node.execution_details["total_count"] = 1
            
        if details is not None:
            node.execution_details.update(details)
            node.metadata.additional_data["failure_fingerprint"] = details.get("failure_fingerprint")
            node.metadata.additional_data["failure_category"] = details.get("failure_category")
            node.metadata.additional_data["last_http_status"] = details.get("http_status")
            node.metadata.additional_data["last_artifacts"] = details.get("artifacts", [])
            
            # AI Fix Intelligence: Generate suggestions based on error
            if status == "FAILED":
                error_msg = str(details.get("error", "")).lower()
                node.suggestions = self._generate_suggestions(error_msg)
            
        if execution_record:
            node.metadata.additional_data["last_run"] = execution_record
            runs = node.metadata.additional_data.setdefault("execution_runs", [])
            run_id = execution_record.get("run_id")
            if run_id:
                runs[:] = [run for run in runs if run.get("run_id") != run_id]
                runs.append(execution_record)
            else:
                runs.append(execution_record)

            self._dedupe_execution_runs(runs)
            if len(runs) > 20:
                del runs[:-20]

            node.metadata.execution_history = [
                run.get("status")
                for run in runs
                if run.get("status")
            ][-10:]
            return

        # Maintain rolling history when no rich execution record is available.
        if not hasattr(node.metadata, 'execution_history'):
            node.metadata.execution_history = []

        node.metadata.execution_history.append(status)
        if len(node.metadata.execution_history) > 10:
            node.metadata.execution_history.pop(0)

    def _dedupe_execution_runs(self, runs: List[Dict[str, Any]]) -> None:
        seen = set()
        deduped = []
        for run in reversed(runs):
            run_id = run.get("run_id")
            dedupe_key = run_id or (run.get("status"), run.get("scenario_name"), run.get("feature_uri"))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            deduped.append(run)
        runs[:] = list(reversed(deduped))

    def _propagate_status_to_parents(self, node_id: str):
        """Propagate status up and aggregate failure counts for structural nodes."""
        # Find all parent nodes that have an edge pointing TO this node
        parents = [edge.from_node for edge in self.graph.edges.values() if edge.to_node == node_id]
        
        for parent_id in parents:
            parent = self.graph.nodes.get(parent_id)
            if not parent:
                continue
            
            # Find all direct children of this parent by looking at global edges
            child_ids = [edge.to_node for edge in self.graph.edges.values() if edge.from_node == parent_id]
            children = [self.graph.nodes[cid] for cid in child_ids if cid in self.graph.nodes]
            
            if not children:
                continue
                
            # Aggregate counts from children
            total_failed = sum(c.execution_details.get("failed_count", 0) for c in children)
            total_items = sum(c.execution_details.get("total_count", 0) for c in children)
            
            if not parent.execution_details:
                parent.execution_details = {}
                
            parent.execution_details["failed_count"] = total_failed
            parent.execution_details["total_count"] = total_items
            
            # Determine new status based on children
            child_statuses = [c.execution_status for c in children if c.execution_status]
            
            if all(s == "PASSED" for s in child_statuses):
                new_status = "PASSED"
            elif all(s == "FAILED" for s in child_statuses):
                new_status = "FAILED"
            elif any(s in ["FAILED", "PARTIAL_FAIL"] for s in child_statuses):
                new_status = "PARTIAL_FAIL"
            else:
                new_status = "NOT_RUN"
                
            if parent.execution_status != new_status:
                parent.execution_status = new_status
                # Recursively propagate up
                self._propagate_status_to_parents(parent_id)

    def _generate_suggestions(self, error_msg: str) -> List[Dict[str, str]]:
        """AI Expert logic to suggest fixes for failures."""
        suggestions = []
        if "status 200 but was 500" in error_msg or "internal server error" in error_msg:
            suggestions.append({
                "description": "Backend System Error (500)",
                "solution": "Check server-side logs for NullPointerException or Database connectivity issues. This is usually a code regression in the service."
            })
        elif "status 200 but was 401" in error_msg or "unauthorized" in error_msg:
            suggestions.append({
                "description": "Authentication Failure (401)",
                "solution": "The test user's session may have expired or permissions were revoked. Check auth token generation logic."
            })
        elif "status 200 but was 404" in error_msg or "not found" in error_msg:
            suggestions.append({
                "description": "API Endpoint Missing (404)",
                "solution": "The API path has likely changed in the latest deployment. Verify the URL mapping in the Common component."
            })
        elif "timeout" in error_msg:
            suggestions.append({
                "description": "Environment Latency / Timeout",
                "solution": "The system response is slower than expected. Check if the environment is under high load or if a database query needs optimization."
            })
        elif "assertion failed" in error_msg:
            suggestions.append({
                "description": "Business Logic Mismatch",
                "solution": "The actual response data differs from the expected value. This indicates a potential logic change in the business requirements."
            })
        
        return suggestions
