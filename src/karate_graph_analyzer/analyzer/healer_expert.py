import logging
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
from karate_graph_analyzer.models import DependencyGraph, Node, NodeType

logger = logging.getLogger(__name__)

class HealerExpert:
    """Expert system for analyzing execution failures and suggesting fixes."""

    def __init__(self, graph: DependencyGraph):
        self.graph = graph

    def suggest_fix(self, node_id: str, error_message: str, project_root: str) -> Dict[str, Any]:
        """Analyze failure and suggest a fix.
        
        Args:
            node_id: ID of the failing component
            error_message: The error message from execution
            project_root: Root path of the project to find source files
            
        Returns:
            Dictionary with analysis and suggestion
        """
        node = self.graph.nodes.get(node_id)
        if not node:
            return {"error": f"Node {node_id} not found in graph"}

        analysis = {
            "node_name": node.name,
            "node_type": node.type.value,
            "error_summary": self._summarize_error(error_message),
            "root_cause": "Unknown",
            "suggestion": "No specific suggestion available.",
            "confidence": 0.3
        }

        # 1. Handle Java-specific failures
        if node.type in [NodeType.JAVA_CLASS, NodeType.JAVA_METHOD]:
            java_suggestion = self._analyze_java_failure(node, error_message, project_root)
            if java_suggestion:
                analysis.update(java_suggestion)

        elif node.type in [NodeType.JAVASCRIPT, NodeType.JS_FUNCTION]:
            analysis.update({
                "root_cause": "JavaScript helper/config failure",
                "suggestion": "Inspect the JS source snippet, exported function name, parameters passed from Karate, and any karate.read/callSingle dependencies.",
                "confidence": 0.6,
            })

        # 2. Handle API-specific failures
        elif node.type == NodeType.API:
            api_suggestion = self._analyze_api_failure(node, error_message)
            if api_suggestion:
                analysis.update(api_suggestion)

        return analysis

    def _summarize_error(self, error: str) -> str:
        """Extract the core error message from a potentially long stacktrace."""
        if not error: return "Empty error message"
        
        # Look for exception name and first line of message
        match = re.search(r'([a-zA-Z\.]+(?:Exception|Error|Failure):.*)', error)
        if match:
            return match.group(1).split('\n')[0]
        
        return error.split('\n')[0]

    def _analyze_java_failure(self, node: Node, error: str, project_root: str) -> Optional[Dict[str, Any]]:
        """Specific analysis for Java interop failures."""
        class_path = node.metadata.additional_data.get("class_path")
        if not class_path:
            return None

        # Try to find the Java file
        java_file = self._find_java_file(class_path, project_root)
        
        # Pattern matching for common Java errors in Karate
        if "NullPointerException" in error:
            return {
                "root_cause": "NullPointerException in Java code",
                "suggestion": f"Check line in {class_path} where an object is used without being initialized. If this is a Karate utility, ensure all required variables are passed to the Java constructor or method.",
                "confidence": 0.8,
                "file_path": str(java_file) if java_file else None
            }
        
        if "NoSuchMethodError" in error or "no such method" in error.lower():
            method_name = node.metadata.additional_data.get("method_name", "unknown")
            return {
                "root_cause": f"Method '{method_name}' not found in {class_path}",
                "suggestion": f"Verify that the method '{method_name}' exists and is public in {class_path}. Check for parameter type mismatches between Karate and Java.",
                "confidence": 0.9,
                "file_path": str(java_file) if java_file else None
            }

        if "ClassNotFoundException" in error:
            return {
                "root_cause": f"Java class {class_path} not found",
                "suggestion": f"Ensure the class {class_path} is compiled and available in the classpath. Check for typos in Java.type() or karate-config.js.",
                "confidence": 1.0
            }

        return None

    def _analyze_api_failure(self, node: Node, error: str) -> Optional[Dict[str, Any]]:
        """Specific analysis for API failures."""
        status_match = re.search(r'status code: (\d+)', error)
        if status_match:
            status = int(status_match.group(1))
            if status == 401:
                return {
                    "root_cause": "Authentication failure (401)",
                    "suggestion": "Check if the access token has expired or is missing from the request headers.",
                    "confidence": 0.9
                }
            if status == 404:
                return {
                    "root_cause": "Endpoint not found (404)",
                    "suggestion": f"Verify the URL path for {node.name}. The endpoint may have changed or the base URL is incorrect.",
                    "confidence": 0.9
                }
            if status >= 500:
                return {
                    "root_cause": f"Server Error ({status})",
                    "suggestion": "The backend service is failing. Check the server logs for internal exceptions.",
                    "confidence": 0.7
                }

        return None

    def _find_java_file(self, class_path: str, project_root: str) -> Optional[Path]:
        """Convert com.bank.Utils to src/main/java/com/bank/Utils.java or similar."""
        rel_path = class_path.replace('.', '/') + ".java"
        
        # Common source directories
        search_dirs = ["src/main/java", "src/test/java", "src/java"]
        
        root = Path(project_root)
        for d in search_dirs:
            full_path = root / d / rel_path
            if full_path.exists():
                return full_path
                
        return None
