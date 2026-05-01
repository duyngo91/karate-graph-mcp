"""
Search and query tools for MCP interface.

Provides search/query methods that can be exposed via MCP.
"""

import logging
from typing import Any, Dict, List, Optional

from karate_graph_analyzer.graph.graph_query import GraphQuery
from karate_graph_analyzer.models import DependencyGraph, Node

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
        try:
            query_api = self._get_query_api(project_name)
            if not query_api:
                return {
                    "success": False,
                    "error": {
                        "code": "7001",
                        "message": f"Project '{project_name}' not found"
                    }
                }
            
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
                nodes = query_api.find_nodes_by_name_pattern(path, node_type=None)
                api_nodes = [n for n in nodes if n.type.value == "API"]
                results = [self._node_to_dict(n, query_api) for n in api_nodes]
            
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }
        
        except Exception as e:
            logger.error(f"Error in search_api: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "7002",
                    "message": str(e)
                }
            }
    
    def search_workflow(
        self,
        project_name: str,
        path: Optional[str] = None,
        scenario_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for workflows and scenarios.
        
        Args:
            project_name: Name of the project
            path: Workflow file path pattern
            scenario_tag: Scenario tag (e.g., '@AddPayment')
        
        Returns:
            Dictionary with search results
        """
        try:
            query_api = self._get_query_api(project_name)
            if not query_api:
                return {
                    "success": False,
                    "error": {
                        "code": "7001",
                        "message": f"Project '{project_name}' not found"
                    }
                }
            
            results = []
            
            # Search by scenario tag
            if scenario_tag:
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
            
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }
        
        except Exception as e:
            logger.error(f"Error in search_workflow: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "7002",
                    "message": str(e)
                }
            }
    
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
        try:
            query_api = self._get_query_api(project_name)
            if not query_api:
                return {
                    "success": False,
                    "error": {
                        "code": "7001",
                        "message": f"Project '{project_name}' not found"
                    }
                }
            
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
            
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }
        
        except Exception as e:
            logger.error(f"Error in search_page: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "7002",
                    "message": str(e)
                }
            }
    
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
        try:
            query_api = self._get_query_api(project_name)
            if not query_api:
                return {
                    "success": False,
                    "error": {
                        "code": "7001",
                        "message": f"Project '{project_name}' not found"
                    }
                }
            
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
                api_nodes = query_api.find_nodes_by_name_pattern(uses_api, None)
                for api_node in api_nodes:
                    if api_node.type.value == "API":
                        test_cases = query_api.find_test_cases_using_api(api_node)
                        results.extend([self._node_to_dict(tc, query_api) for tc in test_cases])
            
            # Search by workflow usage
            elif uses_workflow:
                workflow_node = query_api.find_workflow_by_path(uses_workflow)
                if workflow_node:
                    test_cases = query_api.find_test_cases_using_workflow(workflow_node)
                    results = [self._node_to_dict(tc, query_api) for tc in test_cases]
            
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }
        
        except Exception as e:
            logger.error(f"Error in search_test_case: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "7002",
                    "message": str(e)
                }
            }
    
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
        try:
            query_api = self._get_query_api(project_name)
            if not query_api:
                return {
                    "success": False,
                    "error": {
                        "code": "7001",
                        "message": f"Project '{project_name}' not found"
                    }
                }
            
            node = query_api.find_node_by_id(node_id)
            if not node:
                return {
                    "success": False,
                    "error": {
                        "code": "7003",
                        "message": f"Node '{node_id}' not found"
                    }
                }
            
            stats = query_api.get_usage_stats(node)
            
            return {
                "success": True,
                "stats": stats
            }
        
        except Exception as e:
            logger.error(f"Error in get_usage_stats: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "7002",
                    "message": str(e)
                }
            }
    
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
        try:
            query_api = self._get_query_api(project_name)
            if not query_api:
                return {
                    "success": False,
                    "error": {
                        "code": "7001",
                        "message": f"Project '{project_name}' not found"
                    }
                }
            
            if component_type.lower() == 'api':
                components = query_api.get_most_used_apis(limit)
            elif component_type.lower() == 'workflow':
                components = query_api.get_most_used_workflows(limit)
            else:
                return {
                    "success": False,
                    "error": {
                        "code": "7004",
                        "message": f"Invalid component_type: {component_type}. Must be 'api' or 'workflow'"
                    }
                }
            
            results = [
                {
                    "node": self._node_to_dict(node, query_api),
                    "usage_count": count
                }
                for node, count in components
            ]
            
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }
        
        except Exception as e:
            logger.error(f"Error in get_most_used_components: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "7002",
                    "message": str(e)
                }
            }
    
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
        try:
            query_api = self._get_query_api(project_name)
            if not query_api:
                return {
                    "success": False,
                    "error": {
                        "code": "7001",
                        "message": f"Project '{project_name}' not found"
                    }
                }
            
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
        
        except Exception as e:
            logger.error(f"Error in find_unused_components: {e}", exc_info=True)
            return {
                "success": False,
                "error": {
                    "code": "7002",
                    "message": str(e)
                }
            }
    
    def _node_to_dict(self, node: Node, query_api: GraphQuery) -> Dict[str, Any]:
        """Convert node to dictionary with usage info.
        
        Args:
            node: Node to convert
            query_api: GraphQuery instance for getting usage info
        
        Returns:
            Dictionary representation of node
        """
        usage_count = len(query_api.outgoing.get(node.id, []))
        
        return {
            "id": node.id,
            "type": node.type.value,
            "name": node.name,
            "file_path": node.metadata.file_path,
            "line_number": node.metadata.line_number,
            "jira_tags": node.metadata.jira_tags,
            "usage_count": usage_count,
            "metadata": node.metadata.additional_data
        }
