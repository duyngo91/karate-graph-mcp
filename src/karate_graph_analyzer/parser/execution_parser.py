import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from karate_graph_analyzer.models import DependencyGraph, NodeType, DependencyType

logger = logging.getLogger(__name__)

class ExecutionReportParser:
    """Parses Karate execution reports and maps results to graph nodes."""

    def __init__(self, graph: DependencyGraph):
        self.graph = graph

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
        # Feature name and relative path
        feature_name = feature.get("name")
        feature_uri = feature.get("uri", "") # Usually relative to project root
        
        scenarios = feature.get("elements", [])
        if not scenarios:
            # Check for alternate summary format
            scenarios = feature.get("scenarios", [])
            
        applied = False
        for scenario_data in scenarios:
            if scenario_data.get("type") != "scenario" and "name" not in scenario_data:
                continue
                
            scenario_name = scenario_data.get("name")
            passed = scenario_data.get("passed", True)
            if "status" in scenario_data:
                passed = scenario_data.get("status") == "passed"
            elif "result" in scenario_data:
                passed = scenario_data.get("result", {}).get("status") == "passed"

            status = "PASSED" if passed else "FAILED"
            
            # Map to graph nodes
            # We match by:
            # 1. Exact match of scenario name
            # 2. Case-insensitive partial match (e.g., "@Tag - Scenario Name" matches "Scenario Name")
            
            matched = False
            for node in self.graph.nodes.values():
                if node.type not in [NodeType.SCENARIO, NodeType.TEST_CASE]:
                    continue
                
                # Check if it's the right file and right scenario
                node_file = node.metadata.file_path or ""
                
                # Normalize names for comparison
                n_name = node.name.lower()
                s_name = scenario_name.lower()
                
                name_match = (s_name == n_name) or (s_name in n_name) or (n_name in s_name)
                
                if name_match:
                    # If we have URI info, try to use it for better precision
                    # Feature URI usually looks like 'api/order.feature'
                    # Node file usually looks like 'e:/path/to/api/order.feature'
                    if feature_uri:
                        norm_uri = feature_uri.replace("\\", "/")
                        norm_node_file = node_file.replace("\\", "/")
                        if norm_uri not in norm_node_file and norm_node_file not in norm_uri:
                            # Only skip if we have a strong URI mismatch
                            # But be lenient if one of them is empty
                            if norm_uri and norm_node_file:
                                continue
                        
                    details = None
                    if not passed:
                        details = {
                            "error": scenario_data.get("error_message", "Unknown error"),
                            "failed_step": self._find_failed_step(scenario_data)
                        }
                    self._update_node_status(node.id, status, details)
                    matched = True
                    applied = True
            
            if not matched:
                logger.debug(f"Could not map scenario '{scenario_name}' in '{feature_uri}' to any graph node")
                
        return applied

    def _find_failed_step(self, scenario_data: Dict[str, Any]) -> Optional[str]:
        """Extract the name of the step that failed."""
        steps = scenario_data.get("steps", [])
        for step in steps:
            result = step.get("result", {})
            if result.get("status") == "failed":
                return f"{step.get('keyword', '')} {step.get('name', '')}"
        return None

    def _update_node_status(self, node_id: str, status: str, details: Optional[Dict] = None):
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
            
            # AI Fix Intelligence: Generate suggestions based on error
            if status == "FAILED":
                error_msg = str(details.get("error", "")).lower()
                node.suggestions = self._generate_suggestions(error_msg)
            
        # Maintain rolling history
        if not hasattr(node.metadata, 'execution_history'):
            node.metadata.execution_history = []
            
        node.metadata.execution_history.append(status)
        if len(node.metadata.execution_history) > 10:
            node.metadata.execution_history.pop(0)

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
