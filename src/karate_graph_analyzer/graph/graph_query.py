"""
Graph query API for fast lookups and searches.

Provides high-level query methods for common search patterns.
"""

from typing import Dict, List, Optional, Tuple
from karate_graph_analyzer.models import (
    DependencyGraph,
    Node,
    NodeType,
    Edge,
    InvertedIndices,
)


class GraphQuery:
    """High-level query API for dependency graph."""
    
    def __init__(self, graph: DependencyGraph):
        """Initialize query API with graph.
        
        Args:
            graph: Dependency graph to query
        """
        self.graph = graph
        self.indices = InvertedIndices()
        self.indices.build_from_graph(graph)
        
        # Build adjacency lists for fast traversal
        self._build_adjacency_lists()
    
    def _build_adjacency_lists(self) -> None:
        """Build adjacency lists for fast graph traversal."""
        self.outgoing: Dict[str, List[str]] = {}  # node_id → [target_node_ids]
        self.incoming: Dict[str, List[str]] = {}  # node_id → [source_node_ids]
        
        for edge in self.graph.edges.values():
            # Outgoing edges
            if edge.from_node not in self.outgoing:
                self.outgoing[edge.from_node] = []
            self.outgoing[edge.from_node].append(edge.to_node)
            
            # Incoming edges
            if edge.to_node not in self.incoming:
                self.incoming[edge.to_node] = []
            self.incoming[edge.to_node].append(edge.from_node)
    
    # ========== Node Lookup Methods ==========
    
    def find_node_by_id(self, node_id: str) -> Optional[Node]:
        """Find node by ID.
        
        Args:
            node_id: Node ID to find
        
        Returns:
            Node if found, None otherwise
        """
        return self.graph.nodes.get(node_id)
    
    def find_nodes_by_name(self, name: str, node_type: Optional[NodeType] = None) -> List[Node]:
        """Find nodes by name (exact match).
        
        Args:
            name: Node name to search for
            node_type: Optional node type filter
        
        Returns:
            List of matching nodes
        """
        results = []
        for node in self.graph.nodes.values():
            if node.name == name:
                if node_type is None or node.type == node_type:
                    results.append(node)
        return results
    
    def find_nodes_by_name_pattern(self, pattern: str, node_type: Optional[NodeType] = None) -> List[Node]:
        """Find nodes by name pattern (case-insensitive substring match).
        
        Args:
            pattern: Pattern to search for in node names
            node_type: Optional node type filter
        
        Returns:
            List of matching nodes
        """
        pattern_lower = pattern.lower()
        results = []
        for node in self.graph.nodes.values():
            if pattern_lower in node.name.lower():
                if node_type is None or node.type == node_type:
                    results.append(node)
        return results
    
    # ========== API Query Methods ==========
    
    def find_api_by_method_and_path(self, method: str, path: str) -> Optional[Node]:
        """Find API node by HTTP method and path.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: API path (e.g., '/api/v2/payment')
        
        Returns:
            API node if found, None otherwise
        """
        # Search by HTTP method first (faster with index)
        api_node_ids = self.indices.get_by_http_method(method.upper())
        
        for node_id in api_node_ids:
            node = self.graph.nodes.get(node_id)
            if node:
                full_url = node.metadata.additional_data.get('full_url', '')
                if path in full_url:
                    return node
        
        return None
    
    def find_apis_by_domain(self, domain: str) -> List[Node]:
        """Find all API nodes for a domain.
        
        Args:
            domain: Domain name (e.g., 'ecommerce-api.example.com')
        
        Returns:
            List of API nodes
        """
        node_ids = self.indices.get_by_domain(domain)
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]
    
    def find_apis_by_method(self, method: str) -> List[Node]:
        """Find all API nodes with specific HTTP method.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        
        Returns:
            List of API nodes
        """
        node_ids = self.indices.get_by_http_method(method.upper())
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]
    
    # ========== Workflow/Scenario Query Methods ==========
    
    def find_workflow_by_path(self, path: str) -> Optional[Node]:
        """Find workflow node by file path.
        
        Args:
            path: Workflow file path (e.g., 'common/services/PaymentServices.feature')
        
        Returns:
            Workflow node if found, None otherwise
        """
        for node in self.graph.nodes.values():
            if node.type == NodeType.WORKFLOW:
                if node.name == path or path in node.name:
                    return node
        return None
    
    def find_scenario_by_tag(self, tag: str) -> List[Node]:
        """Find scenario nodes by tag.
        
        Args:
            tag: Scenario tag (e.g., '@AddPayment', 'AddPayment')
        
        Returns:
            List of scenario nodes
        """
        # Normalize tag (add @ if missing)
        if not tag.startswith('@'):
            tag = f'@{tag}'
        
        node_ids = self.indices.get_by_scenario_tag(tag)
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]
    
    def find_scenarios_in_workflow(self, workflow_node: Node) -> List[Node]:
        """Find all scenario nodes in a workflow.
        
        Args:
            workflow_node: Workflow node
        
        Returns:
            List of scenario nodes
        """
        # Get outgoing edges from workflow
        target_ids = self.outgoing.get(workflow_node.id, [])
        
        scenarios = []
        for target_id in target_ids:
            node = self.graph.nodes.get(target_id)
            if node and node.type == NodeType.SCENARIO:
                scenarios.append(node)
        
        return scenarios
    
    # ========== Page/Action Query Methods ==========
    
    def find_page_by_path(self, path: str) -> Optional[Node]:
        """Find page node by file path.
        
        Args:
            path: Page file path (e.g., 'web/pages/LoginPage.feature')
        
        Returns:
            Page node if found, None otherwise
        """
        for node in self.graph.nodes.values():
            if node.type == NodeType.PAGE:
                if node.name == path or path in node.name:
                    return node
        return None
    
    def find_action_by_tag(self, tag: str) -> List[Node]:
        """Find action nodes by tag.
        
        Args:
            tag: Action tag (e.g., '@login', 'login')
        
        Returns:
            List of action nodes
        """
        # Normalize tag (add @ if missing)
        if not tag.startswith('@'):
            tag = f'@{tag}'
        
        node_ids = self.indices.get_by_action_tag(tag)
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]
    
    def find_actions_in_page(self, page_node: Node) -> List[Node]:
        """Find all action nodes in a page.
        
        Args:
            page_node: Page node
        
        Returns:
            List of action nodes
        """
        # Get outgoing edges from page
        target_ids = self.outgoing.get(page_node.id, [])
        
        actions = []
        for target_id in target_ids:
            node = self.graph.nodes.get(target_id)
            if node and node.type == NodeType.ACTION:
                actions.append(node)
        
        return actions
    
    # ========== Test Case Query Methods ==========
    
    def find_test_cases_by_jira_tag(self, jira_tag: str) -> List[Node]:
        """Find test cases by Jira tag.
        
        Args:
            jira_tag: Jira tag (e.g., '@JiraId-123', 'JiraId-123')
        
        Returns:
            List of test case nodes
        """
        # Normalize tag (add @ if missing)
        if not jira_tag.startswith('@'):
            jira_tag = f'@{jira_tag}'
        
        node_ids = self.indices.get_by_jira_tag(jira_tag)
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]
    
    def find_test_cases_using_api(self, api_node: Node) -> List[Node]:
        """Find all test cases that use an API.
        
        Args:
            api_node: API node
        
        Returns:
            List of test case nodes
        """
        # Get outgoing edges from API (API → Test Case)
        target_ids = self.outgoing.get(api_node.id, [])
        
        test_cases = []
        for target_id in target_ids:
            node = self.graph.nodes.get(target_id)
            if node and node.type == NodeType.TEST_CASE:
                test_cases.append(node)
        
        return test_cases
    
    def find_test_cases_using_workflow(self, workflow_node: Node) -> List[Node]:
        """Find all test cases that use a workflow.
        
        Args:
            workflow_node: Workflow node
        
        Returns:
            List of test case nodes
        """
        # Workflows may have scenarios in between
        # Path: Workflow → Scenario → Test Case
        test_cases = []
        
        # Get scenarios in workflow
        scenarios = self.find_scenarios_in_workflow(workflow_node)
        
        if scenarios:
            # Get test cases from scenarios
            for scenario in scenarios:
                target_ids = self.outgoing.get(scenario.id, [])
                for target_id in target_ids:
                    node = self.graph.nodes.get(target_id)
                    if node and node.type == NodeType.TEST_CASE:
                        test_cases.append(node)
        else:
            # Direct connection: Workflow → Test Case (legacy)
            target_ids = self.outgoing.get(workflow_node.id, [])
            for target_id in target_ids:
                node = self.graph.nodes.get(target_id)
                if node and node.type == NodeType.TEST_CASE:
                    test_cases.append(node)
        
        return test_cases
    
    def find_test_cases_using_scenario(self, scenario_node: Node) -> List[Node]:
        """Find all test cases that use a scenario.
        
        Args:
            scenario_node: Scenario node
        
        Returns:
            List of test case nodes
        """
        # Get outgoing edges from scenario (Scenario → Test Case)
        target_ids = self.outgoing.get(scenario_node.id, [])
        
        test_cases = []
        for target_id in target_ids:
            node = self.graph.nodes.get(target_id)
            if node and node.type == NodeType.TEST_CASE:
                test_cases.append(node)
        
        return test_cases
    
    def find_test_cases_using_page(self, page_node: Node) -> List[Node]:
        """Find all test cases that use a page.
        
        Args:
            page_node: Page node
        
        Returns:
            List of test case nodes
        """
        # Pages may have actions in between
        # Path: Page → Action → Test Case
        test_cases = []
        
        # Get actions in page
        actions = self.find_actions_in_page(page_node)
        
        if actions:
            # Get test cases from actions
            for action in actions:
                target_ids = self.outgoing.get(action.id, [])
                for target_id in target_ids:
                    node = self.graph.nodes.get(target_id)
                    if node and node.type == NodeType.TEST_CASE:
                        test_cases.append(node)
        else:
            # Direct connection: Page → Test Case (legacy)
            target_ids = self.outgoing.get(page_node.id, [])
            for target_id in target_ids:
                node = self.graph.nodes.get(target_id)
                if node and node.type == NodeType.TEST_CASE:
                    test_cases.append(node)
        
        return test_cases
    
    # ========== Usage Statistics Methods ==========
    
    def get_usage_stats(self, node: Node) -> Dict:
        """Get usage statistics for a node.
        
        Args:
            node: Node to get stats for
        
        Returns:
            Dictionary with usage statistics
        """
        stats = {
            "node_id": node.id,
            "node_type": node.type.value,
            "node_name": node.name,
            "usage_count": 0,
            "used_by_test_cases": [],
            "direct_dependencies": [],
        }
        
        # Get outgoing edges (dependencies)
        target_ids = self.outgoing.get(node.id, [])
        stats["usage_count"] = len(target_ids)
        
        # Collect test cases and other dependencies
        for target_id in target_ids:
            target_node = self.graph.nodes.get(target_id)
            if target_node:
                if target_node.type == NodeType.TEST_CASE:
                    stats["used_by_test_cases"].append({
                        "id": target_node.id,
                        "name": target_node.name,
                        "jira_tags": target_node.metadata.jira_tags
                    })
                else:
                    stats["direct_dependencies"].append({
                        "id": target_node.id,
                        "type": target_node.type.value,
                        "name": target_node.name
                    })
        
        # For workflows/pages, also count scenarios/actions
        if node.type == NodeType.WORKFLOW:
            scenarios = self.find_scenarios_in_workflow(node)
            stats["scenarios_count"] = len(scenarios)
            stats["scenarios"] = [
                {
                    "id": s.id,
                    "tag": s.metadata.additional_data.get('scenario_tag'),
                    "usage_count": len(self.outgoing.get(s.id, []))
                }
                for s in scenarios
            ]
        elif node.type == NodeType.PAGE:
            actions = self.find_actions_in_page(node)
            stats["actions_count"] = len(actions)
            stats["actions"] = [
                {
                    "id": a.id,
                    "tag": a.metadata.additional_data.get('action_tag'),
                    "usage_count": len(self.outgoing.get(a.id, []))
                }
                for a in actions
            ]
        
        return stats
    
    def get_most_used_apis(self, limit: int = 10) -> List[Tuple[Node, int]]:
        """Get most used API endpoints.
        
        Args:
            limit: Maximum number of results
        
        Returns:
            List of (node, usage_count) tuples, sorted by usage count descending
        """
        api_usage = []
        
        for node in self.graph.nodes.values():
            if node.type == NodeType.API:
                usage_count = len(self.outgoing.get(node.id, []))
                api_usage.append((node, usage_count))
        
        # Sort by usage count descending
        api_usage.sort(key=lambda x: x[1], reverse=True)
        
        return api_usage[:limit]
    
    def get_most_used_workflows(self, limit: int = 10) -> List[Tuple[Node, int]]:
        """Get most used workflows.
        
        Args:
            limit: Maximum number of results
        
        Returns:
            List of (node, usage_count) tuples, sorted by usage count descending
        """
        workflow_usage = []
        
        for node in self.graph.nodes.values():
            if node.type == NodeType.WORKFLOW:
                # Count test cases using this workflow (via scenarios or direct)
                test_cases = self.find_test_cases_using_workflow(node)
                usage_count = len(test_cases)
                workflow_usage.append((node, usage_count))
        
        # Sort by usage count descending
        workflow_usage.sort(key=lambda x: x[1], reverse=True)
        
        return workflow_usage[:limit]
    
    def get_unused_components(self) -> Dict[str, List[Node]]:
        """Find unused components (workflows, pages, APIs with no test cases).
        
        Returns:
            Dictionary mapping component type to list of unused nodes
        """
        unused = {
            "workflows": [],
            "pages": [],
            "apis": [],
            "scenarios": [],
            "actions": []
        }
        
        for node in self.graph.nodes.values():
            # Check if node has no outgoing edges (not used by anyone)
            if not self.outgoing.get(node.id):
                if node.type == NodeType.WORKFLOW:
                    unused["workflows"].append(node)
                elif node.type == NodeType.PAGE:
                    unused["pages"].append(node)
                elif node.type == NodeType.API:
                    unused["apis"].append(node)
                elif node.type == NodeType.SCENARIO:
                    unused["scenarios"].append(node)
                elif node.type == NodeType.ACTION:
                    unused["actions"].append(node)
        
        return unused
