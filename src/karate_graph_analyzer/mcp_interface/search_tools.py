"""
Search and query tools for MCP interface.

Provides search/query methods that can be exposed via MCP.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from karate_graph_analyzer.graph.graph_query import GraphQuery
from karate_graph_analyzer.models import DependencyGraph, Node, NodeType
from karate_graph_analyzer.utils.source_snippet import get_source_snippet

logger = logging.getLogger(__name__)


class SearchTools:
    """Search and query tools for graph analysis."""
    
    def __init__(self, graphs: Dict[str, DependencyGraph]):
        """Initialize search tools.
        
        Args:
            graphs: Dictionary mapping project_name to DependencyGraph
        """
        self.graphs = graphs
        self.query_apis: Dict[str, GraphQuery] = {}  # project_name -> GraphQuery
    
    def _get_query_api(self, project_name: str) -> Optional[GraphQuery]:
        """Get or create GraphQuery API for a project.
        
        Args:
            project_name: Name of the project
        
        Returns:
            GraphQuery instance or None if project not found
        """
        if project_name not in self.graphs:
            return None
        
        if project_name not in self.query_apis:
            self.query_apis[project_name] = GraphQuery(self.graphs[project_name])
        
        return self.query_apis[project_name]

    def _error_response(self, code: str, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "error": {
                "code": code,
                "message": message
            }
        }

    def _project_not_found(self, project_name: str) -> Dict[str, Any]:
        return self._error_response("7001", f"Project '{project_name}' not found")

    def _query_error(self, operation: str, error: Exception) -> Dict[str, Any]:
        logger.error(f"Error in {operation}: {error}", exc_info=True)
        return self._error_response("7002", str(error))

    def _run_project_query(
        self,
        project_name: str,
        operation: str,
        handler: Callable[[GraphQuery], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Run a query method with consistent project lookup and error handling."""
        try:
            query_api = self._get_query_api(project_name)
            if not query_api:
                return self._project_not_found(project_name)
            return handler(query_api)
        except Exception as e:
            return self._query_error(operation, e)

    def _results_response(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "success": True,
            "results": results,
            "count": len(results)
        }

    def _api_matches_pattern(self, node: Node, pattern: str) -> bool:
        data = node.metadata.additional_data
        candidates = [
            node.name,
            data.get("full_url", ""),
            data.get("path", ""),
            data.get("path_template", ""),
        ]
        return any(pattern.lower() in candidate.lower() for candidate in candidates)

    def _find_api_nodes_by_pattern(self, query_api: GraphQuery, pattern: str) -> List[Node]:
        return [
            node for node in query_api.nodes_by_type.get(NodeType.API, [])
            if node.type.value == "API" and self._api_matches_pattern(node, pattern)
        ]
    
    def search_api(
        self,
        project_name: str,
        method: Optional[str] = None,
        path: Optional[str] = None,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for API endpoints.
        
        Args:
            project_name: Name of the project
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: API path pattern
            domain: Domain name
        
        Returns:
            Dictionary with search results
        """
        def query(query_api: GraphQuery) -> Dict[str, Any]:
            results = []
            
            # Search by method and path
            if method and path:
                node = query_api.find_api_by_method_and_path(method, path)
                if node:
                    results.append(self._node_to_dict(node, query_api))
            
            # Search by domain
            elif domain:
                nodes = query_api.find_apis_by_domain(domain)
                results = [self._node_to_dict(n, query_api) for n in nodes]
            
            # Search by method only
            elif method:
                nodes = query_api.find_apis_by_method(method)
                results = [self._node_to_dict(n, query_api) for n in nodes]
            
            # Search by path pattern
            elif path:
                api_nodes = self._find_api_nodes_by_pattern(query_api, path)
                results = [self._node_to_dict(n, query_api) for n in api_nodes]
            
            return self._results_response(results)

        return self._run_project_query(project_name, "search_api", query)
    
    def search_workflow(
        self,
        project_name: str,
        path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        keyword: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for workflows and scenarios.
        
        Args:
            project_name: Name of the project
            path: Workflow file path pattern
            scenario_tag: Scenario tag (e.g., '@AddPayment')
        
        Returns:
            Dictionary with search results
        """
        def query(query_api: GraphQuery) -> Dict[str, Any]:
            results = []
            
            # Search by keyword
            if keyword:
                nodes = query_api.find_workflows_by_keyword(keyword)
                results = [self._node_to_dict(n, query_api) for n in nodes]
            
            # Search by scenario tag
            elif scenario_tag:
                nodes = query_api.find_scenario_by_tag(scenario_tag)
                results = [self._node_to_dict(n, query_api) for n in nodes]
            
            # Search by workflow path
            elif path:
                node = query_api.find_workflow_by_path(path)
                if node:
                    result = self._node_to_dict(node, query_api)
                    # Add scenarios in this workflow
                    scenarios = query_api.find_scenarios_in_workflow(node)
                    result["scenarios"] = [
                        {
                            "id": s.id,
                            "tag": s.metadata.additional_data.get('scenario_tag'),
                            "usage_count": len(query_api.outgoing.get(s.id, []))
                        }
                        for s in scenarios
                    ]
                    results.append(result)
            
            return self._results_response(results)

        return self._run_project_query(project_name, "search_workflow", query)
    
    def search_page(
        self,
        project_name: str,
        path: Optional[str] = None,
        action_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for pages and actions.
        
        Args:
            project_name: Name of the project
            path: Page file path pattern
            action_tag: Action tag (e.g., '@login')
        
        Returns:
            Dictionary with search results
        """
        def query(query_api: GraphQuery) -> Dict[str, Any]:
            results = []
            
            # Search by action tag
            if action_tag:
                nodes = query_api.find_action_by_tag(action_tag)
                results = [self._node_to_dict(n, query_api) for n in nodes]
            
            # Search by page path
            elif path:
                node = query_api.find_page_by_path(path)
                if node:
                    result = self._node_to_dict(node, query_api)
                    # Add actions in this page
                    actions = query_api.find_actions_in_page(node)
                    result["actions"] = [
                        {
                            "id": a.id,
                            "tag": a.metadata.additional_data.get('action_tag'),
                            "usage_count": len(query_api.outgoing.get(a.id, []))
                        }
                        for a in actions
                    ]
                    results.append(result)
            
            return self._results_response(results)

        return self._run_project_query(project_name, "search_page", query)
    
    def search_test_case(
        self,
        project_name: str,
        jira_tag: Optional[str] = None,
        name_pattern: Optional[str] = None,
        uses_api: Optional[str] = None,
        uses_workflow: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for test cases.
        
        Args:
            project_name: Name of the project
            jira_tag: Jira tag (e.g., '@JiraId-123')
            name_pattern: Test case name pattern
            uses_api: API endpoint used by test
            uses_workflow: Workflow used by test
        
        Returns:
            Dictionary with search results
        """
        def query(query_api: GraphQuery) -> Dict[str, Any]:
            results = []
            
            # Search by Jira tag
            if jira_tag:
                nodes = query_api.find_test_cases_by_jira_tag(jira_tag)
                results = [self._node_to_dict(n, query_api) for n in nodes]
            
            # Search by name pattern
            elif name_pattern:
                from karate_graph_analyzer.models import NodeType
                nodes = query_api.find_nodes_by_name_pattern(name_pattern, NodeType.TEST_CASE)
                results = [self._node_to_dict(n, query_api) for n in nodes]
            
            # Search by API usage
            elif uses_api:
                # Find API node first
                for api_node in self._find_api_nodes_by_pattern(query_api, uses_api):
                    test_cases = query_api.find_test_cases_using_api(api_node)
                    results.extend([self._node_to_dict(tc, query_api) for tc in test_cases])
            
            # Search by workflow usage
            elif uses_workflow:
                workflow_node = query_api.find_workflow_by_path(uses_workflow)
                if workflow_node:
                    test_cases = query_api.find_test_cases_using_workflow(workflow_node)
                    results = [self._node_to_dict(tc, query_api) for tc in test_cases]
            
            return self._results_response(results)

        return self._run_project_query(project_name, "search_test_case", query)
    
    def get_usage_stats(
        self,
        project_name: str,
        node_id: str
    ) -> Dict[str, Any]:
        """Get usage statistics for a node.
        
        Args:
            project_name: Name of the project
            node_id: Node ID
        
        Returns:
            Dictionary with usage statistics
        """
        def query(query_api: GraphQuery) -> Dict[str, Any]:
            node = query_api.find_node_by_id(node_id)
            if not node:
                return self._error_response("7003", f"Node '{node_id}' not found")
            
            stats = query_api.get_usage_stats(node, test_case_limit=100)
            
            return {
                "success": True,
                "stats": stats
            }

        return self._run_project_query(project_name, "get_usage_stats", query)
    
    def get_most_used_components(
        self,
        project_name: str,
        component_type: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get most used components.
        
        Args:
            project_name: Name of the project
            component_type: Type of component ('api', 'workflow', 'page')
            limit: Maximum number of results
        
        Returns:
            Dictionary with most used components
        """
        def query(query_api: GraphQuery) -> Dict[str, Any]:
            if component_type.lower() == 'api':
                components = query_api.get_most_used_apis(limit)
            elif component_type.lower() == 'workflow':
                components = query_api.get_most_used_workflows(limit)
            else:
                return self._error_response(
                    "7004",
                    f"Invalid component_type: {component_type}. Must be 'api' or 'workflow'"
                )
            
            results = [
                {
                    "node": self._node_to_dict(node, query_api),
                    "usage_count": count
                }
                for node, count in components
            ]
            
            return self._results_response(results)

        return self._run_project_query(project_name, "get_most_used_components", query)
    
    def find_unused_components(
        self,
        project_name: str
    ) -> Dict[str, Any]:
        """Find unused components.
        
        Args:
            project_name: Name of the project
        
        Returns:
            Dictionary with unused components by type
        """
        def query(query_api: GraphQuery) -> Dict[str, Any]:
            unused = query_api.get_unused_components()
            
            results = {}
            for component_type, nodes in unused.items():
                results[component_type] = [
                    self._node_to_dict(node, query_api)
                    for node in nodes
                ]
            
            total_count = sum(len(nodes) for nodes in results.values())
            
            return {
                "success": True,
                "unused_components": results,
                "total_count": total_count
            }

        return self._run_project_query(project_name, "find_unused_components", query)

    def search_java_usage(
        self,
        project_name: str,
        query: str,
        include_methods: bool = True,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Search Java class/method usage and their calling test cases."""
        term = (query or "").strip().lower()

        def _matches(node: Node) -> bool:
            haystacks = [
                node.name or "",
                str(node.metadata.additional_data.get("class_path", "")),
                str(node.metadata.additional_data.get("method_name", "")),
                str(node.metadata.file_path or ""),
            ]
            if not term:
                return True
            return any(term in text.lower() for text in haystacks)

        def query_fn(query_api: GraphQuery) -> Dict[str, Any]:
            target_types = {NodeType.JAVA_CLASS}
            if include_methods:
                target_types.add(NodeType.JAVA_METHOD)

            nodes = [
                node
                for node in query_api.nodes_by_type.get(NodeType.JAVA_CLASS, [])
                + query_api.nodes_by_type.get(NodeType.JAVA_METHOD, [])
                if node.type in target_types and _matches(node)
            ]
            results = [self._node_to_dict(node, query_api) for node in nodes]
            results.sort(key=lambda item: (item.get("usage_count", 0), item.get("name", "")), reverse=True)
            return {
                "success": True,
                "results": results[:limit],
                "count": min(len(results), limit),
                "total_available": len(results),
            }

        return self._run_project_query(project_name, "search_java_usage", query_fn)

    def search_js_usage(
        self,
        project_name: str,
        query: str = "",
        include_functions: bool = True,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Search JavaScript file/function usage and their calling test cases."""
        term = (query or "").strip().lower()

        def _matches(node: Node) -> bool:
            haystacks = [
                node.name or "",
                str(node.metadata.additional_data.get("function_name", "")),
                str(node.metadata.additional_data.get("script_path", "")),
                str(node.metadata.file_path or ""),
            ]
            if not term:
                return True
            return any(term in text.lower() for text in haystacks)

        def query_fn(query_api: GraphQuery) -> Dict[str, Any]:
            target_types = {NodeType.JAVASCRIPT}
            if include_functions:
                target_types.add(NodeType.JS_FUNCTION)

            nodes = [
                node
                for node in query_api.nodes_by_type.get(NodeType.JAVASCRIPT, [])
                + query_api.nodes_by_type.get(NodeType.JS_FUNCTION, [])
                if node.type in target_types and _matches(node)
            ]
            results = [self._node_to_dict(node, query_api) for node in nodes]
            results.sort(key=lambda item: (item.get("usage_count", 0), item.get("name", "")), reverse=True)
            return {
                "success": True,
                "results": results[:limit],
                "count": min(len(results), limit),
                "total_available": len(results),
            }

        return self._run_project_query(project_name, "search_js_usage", query_fn)

    def search_error_pattern(
        self,
        project_name: str,
        pattern: str,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Search execution failures by error/fingerprint/failed-step pattern."""
        term = (pattern or "").strip().lower()
        if not term:
            return self._error_response("7005", "Pattern must not be empty")

        def query_fn(query_api: GraphQuery) -> Dict[str, Any]:
            matches: List[Dict[str, Any]] = []
            for node in query_api.graph.nodes.values():
                details = node.execution_details or {}
                additional = node.metadata.additional_data or {}
                display = additional.get("display_data", {}).get("details", {})

                error = (
                    details.get("error")
                    or additional.get("last_error")
                    or display.get("last_error")
                    or ""
                )
                failed_step = details.get("failed_step") or ""
                fingerprint = (
                    details.get("failure_fingerprint")
                    or additional.get("failure_fingerprint")
                    or ""
                )

                searchable = " | ".join(
                    [
                        str(node.name or ""),
                        str(node.type.value),
                        str(error),
                        str(failed_step),
                        str(fingerprint),
                    ]
                ).lower()
                if term not in searchable:
                    continue

                item = self._node_to_dict(node, query_api)
                item.update(
                    {
                        "error_message": error,
                        "failed_step": failed_step,
                        "failure_fingerprint": fingerprint,
                        "execution_status": node.execution_status,
                    }
                )
                matches.append(item)

            matches.sort(
                key=lambda item: (
                    0 if item.get("execution_status") == "FAILED" else 1,
                    -(item.get("usage_count", 0)),
                    item.get("name", ""),
                )
            )
            return {
                "success": True,
                "results": matches[:limit],
                "count": min(len(matches), limit),
                "total_available": len(matches),
            }

        return self._run_project_query(project_name, "search_error_pattern", query_fn)
    
    def _node_to_dict(self, node: Node, query_api: GraphQuery) -> Dict[str, Any]:
        """Convert node to dictionary with usage info.
        
        Args:
            node: Node to convert
            query_api: GraphQuery instance for getting usage info
        
        Returns:
            Dictionary representation of node
        """
        usage_count = query_api.get_usage_count(node)
        
        # Determine test case ID (first Jira tag)
        test_case_id = None
        if node.type.value == "TEST_CASE" and node.metadata.jira_tags:
            test_case_id = node.metadata.jira_tags[0].lstrip('@')
            
        return {
            "id": node.id,
            "type": node.type.value,
            "name": node.name,
            "test_case_id": test_case_id,
            "file_path": node.metadata.file_path,
            "line_number": node.metadata.line_number,
            "jira_tags": node.metadata.jira_tags,
            "usage_count": usage_count,
            "source_snippet": get_source_snippet(node.metadata.file_path, node.metadata.line_number),
            "metadata": node.metadata.additional_data
        }
