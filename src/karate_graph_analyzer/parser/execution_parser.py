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
                if self._apply_single_report(path):
                    total_applied += 1
            except Exception as e:
                logger.error(f"Failed to apply report {path}: {str(e)}")
        
        # Propagate status from SCENARIOS to parent TEST_CASE nodes
        self._propagate_status_to_parents()
        return total_applied

    def _propagate_status_to_parents(self):
        """Update parent nodes (WORKFLOW, COMMON, PAGE) based on child results."""
        # Map parents to their children's statuses
        parent_map = {} # parent_id -> list of statuses
        
        # Valid parent types that have children
        parent_types = [NodeType.WORKFLOW, NodeType.COMMON, NodeType.PAGE]
        # Valid edge types that link parent to child scenarios/actions
        edge_types = [DependencyType.WORKFLOW, DependencyType.COMMON, DependencyType.PAGE]
        
        # 1. Collect statuses from children
        for edge in self.graph.edges.values():
            if edge.type in edge_types:
                parent_node = self.graph.nodes.get(edge.from_node)
                child_node = self.graph.nodes.get(edge.to_node)
                
                if parent_node and parent_node.type in parent_types and child_node and child_node.execution_status:
                    if parent_node.id not in parent_map:
                        parent_map[parent_node.id] = []
                    parent_map[parent_node.id].append(child_node.execution_status)
        
        # 2. Update parent status
        for parent_id, statuses in parent_map.items():
            parent_node = self.graph.nodes.get(parent_id)
            if not parent_node:
                continue
                
            if "FAILED" in statuses:
                parent_node.execution_status = "FAILED"
            elif all(s == "PASSED" for s in statuses):
                parent_node.execution_status = "PASSED"

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
                        
                    node.execution_status = status
                    if not passed:
                        node.execution_details = {
                            "error": scenario_data.get("error_message", "Unknown error"),
                            "failed_step": self._find_failed_step(scenario_data)
                        }
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
