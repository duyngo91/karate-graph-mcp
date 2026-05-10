"""
Graph query API for fast lookups and searches.

Edges in the dependency graph point from caller to callee. In other words,
``TEST_CASE -> API`` means the test case uses the API. Query methods that ask
"who uses this?" therefore traverse incoming edges.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from karate_graph_analyzer.models import DependencyGraph, InvertedIndices, Node, NodeType


class GraphQuery:
    """High-level query API for dependency graph."""

    def __init__(self, graph: DependencyGraph):
        self.graph = graph
        self.indices = InvertedIndices()
        self.indices.build_from_graph(graph)
        self._build_adjacency_lists()
        self.nodes_by_type: Dict[NodeType, List[Node]] = {}
        for node in self.graph.nodes.values():
            self.nodes_by_type.setdefault(node.type, []).append(node)
        self._caller_cache: Dict[str, List[Node]] = {}
        self._usage_index: Optional[Dict[str, Set[str]]] = None
        self._direct_dependency_cache: Dict[str, List[Dict[str, Any]]] = {}

    def _build_adjacency_lists(self) -> None:
        self.outgoing: Dict[str, List[str]] = {}
        self.incoming: Dict[str, List[str]] = {}

        for edge in self.graph.edges.values():
            self.outgoing.setdefault(edge.from_node, []).append(edge.to_node)
            self.incoming.setdefault(edge.to_node, []).append(edge.from_node)

    def _nodes_of_type(self, node_type: NodeType) -> List[Node]:
        return self.nodes_by_type.get(node_type, [])

    def _build_usage_index(self) -> Dict[str, Set[str]]:
        """Build node -> reachable TEST_CASE ids once for broad usage queries."""
        if self._usage_index is not None:
            return self._usage_index

        usage: Dict[str, Set[str]] = {}
        test_cases = self._nodes_of_type(NodeType.TEST_CASE)
        for test_case in test_cases:
            seen: Set[str] = set()
            stack = list(self.outgoing.get(test_case.id, []))
            while stack:
                node_id = stack.pop()
                if node_id in seen:
                    continue
                seen.add(node_id)
                usage.setdefault(node_id, set()).add(test_case.id)
                stack.extend(self.outgoing.get(node_id, []))

        self._usage_index = usage
        self._caller_cache.clear()
        return usage

    def _collect_test_case_callers(self, node_id: str) -> List[Node]:
        """Return TEST_CASE nodes that can reach the dependency node."""
        if node_id in self._caller_cache:
            return self._caller_cache[node_id]

        if self._usage_index is not None:
            result = [
                self.graph.nodes[test_id]
                for test_id in self._usage_index.get(node_id, set())
                if test_id in self.graph.nodes
            ]
            result.sort(key=lambda n: (n.metadata.file_path or "", n.metadata.line_number or 0, n.id))
            self._caller_cache[node_id] = result
            return result

        result: List[Node] = []
        seen = set()
        stack = list(self.incoming.get(node_id, []))

        while stack:
            caller_id = stack.pop()
            if caller_id in seen:
                continue
            seen.add(caller_id)

            node = self.graph.nodes.get(caller_id)
            if node is None:
                continue
            if node.type == NodeType.TEST_CASE:
                result.append(node)
            else:
                stack.extend(self.incoming.get(caller_id, []))

        result.sort(key=lambda n: (n.metadata.file_path or "", n.metadata.line_number or 0, n.id))
        self._caller_cache[node_id] = result
        return result

    def get_usage_count(self, node: Node) -> int:
        """Return how many TEST_CASE nodes can reach this node."""
        if self._usage_index is not None:
            return len(self._usage_index.get(node.id, set()))
        return len(self._collect_test_case_callers(node.id))

    def _direct_dependencies(self, node: Node) -> List[Dict[str, Any]]:
        if node.id in self._direct_dependency_cache:
            return self._direct_dependency_cache[node.id]

        direct_dependencies: List[Dict[str, Any]] = []
        for target_id in self.outgoing.get(node.id, []):
            target_node = self.graph.nodes.get(target_id)
            if target_node:
                direct_dependencies.append(
                    {"id": target_node.id, "type": target_node.type.value, "name": target_node.name}
                )
        self._direct_dependency_cache[node.id] = direct_dependencies
        return direct_dependencies

    def _test_case_payloads(
        self,
        used_by: List[Node],
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        selected = used_by if limit is None else used_by[: max(limit, 0)]
        return [
            {
                "id": n.id,
                "name": n.name,
                "jira_tags": n.metadata.jira_tags,
                "test_case_id": n.metadata.jira_tags[0].lstrip('@') if n.metadata.jira_tags else None,
            }
            for n in selected
        ]

    def _dedupe_nodes(self, nodes: List[Node]) -> List[Node]:
        result: List[Node] = []
        seen = set()
        for node in nodes:
            if node.id in seen:
                continue
            result.append(node)
            seen.add(node.id)
        return result

    # ========== Node Lookup Methods ==========

    def find_node_by_id(self, node_id: str) -> Optional[Node]:
        return self.graph.nodes.get(node_id)

    def find_nodes_by_name(self, name: str, node_type: Optional[NodeType] = None) -> List[Node]:
        nodes = self._nodes_of_type(node_type) if node_type else self.graph.nodes.values()
        return [
            node
            for node in nodes
            if node.name == name and (node_type is None or node.type == node_type)
        ]

    def find_nodes_by_name_pattern(
        self, pattern: str, node_type: Optional[NodeType] = None
    ) -> List[Node]:
        pattern_lower = pattern.lower()
        nodes = self._nodes_of_type(node_type) if node_type else self.graph.nodes.values()
        return [
            node
            for node in nodes
            if pattern_lower in node.name.lower() and (node_type is None or node.type == node_type)
        ]

    # ========== API Query Methods ==========

    def find_api_by_method_and_path(self, method: str, path: str) -> Optional[Node]:
        api_node_ids = self.indices.get_by_http_method(method.upper())

        for node_id in api_node_ids:
            node = self.graph.nodes.get(node_id)
            if not node:
                continue
            data = node.metadata.additional_data
            candidates = [
                data.get("full_url", ""),
                data.get("path", ""),
                data.get("path_template", ""),
                node.name,
            ]
            if any(path in candidate for candidate in candidates):
                return node
        return None

    def find_apis_by_domain(self, domain: str) -> List[Node]:
        node_ids = self.indices.get_by_domain(domain)
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]

    def find_apis_by_method(self, method: str) -> List[Node]:
        node_ids = self.indices.get_by_http_method(method.upper())
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]

    # ========== Workflow/Scenario Query Methods ==========

    def find_workflow_by_path(self, path: str) -> Optional[Node]:
        for node in self._nodes_of_type(NodeType.WORKFLOW):
            if node.name == path or path in node.name:
                return node
        return None

    def find_workflows_by_keyword(self, keyword: str) -> List[Node]:
        """Search workflows and scenarios by keyword in name, tags, or description."""
        keyword_lower = keyword.lower()
        results = []
        for node in self._nodes_of_type(NodeType.WORKFLOW) + self._nodes_of_type(NodeType.SCENARIO):
            if node.type in (NodeType.WORKFLOW, NodeType.SCENARIO):
                # Search in name
                if keyword_lower in node.name.lower():
                    results.append(node)
                    continue
                
                # Search in metadata
                data = node.metadata.additional_data
                if 'scenario_tag' in data and keyword_lower in data['scenario_tag'].lower():
                    results.append(node)
                    continue
                if 'tags' in data and any(keyword_lower in tag.lower() for tag in data['tags']):
                    results.append(node)
                    continue
                if 'steps' in data and any(keyword_lower in step.lower() for step in data['steps']):
                    results.append(node)
                    continue
        return results

    def find_scenario_by_tag(self, tag: str) -> List[Node]:
        if not tag.startswith("@"):
            tag = f"@{tag}"

        node_ids = self.indices.get_by_scenario_tag(tag)
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]

    def find_scenarios_in_workflow(self, workflow_node: Node) -> List[Node]:
        scenarios = []
        for target_id in self.outgoing.get(workflow_node.id, []):
            node = self.graph.nodes.get(target_id)
            if node and node.type == NodeType.SCENARIO:
                scenarios.append(node)
        return scenarios

    # ========== Page/Action Query Methods ==========

    def find_page_by_path(self, path: str) -> Optional[Node]:
        for node in self._nodes_of_type(NodeType.PAGE):
            if node.name == path or path in node.name:
                return node
        return None

    def find_action_by_tag(self, tag: str) -> List[Node]:
        if not tag.startswith("@"):
            tag = f"@{tag}"

        node_ids = self.indices.get_by_action_tag(tag)
        return [self.graph.nodes[nid] for nid in node_ids if nid in self.graph.nodes]

    def find_actions_in_page(self, page_node: Node) -> List[Node]:
        actions = []
        for target_id in self.outgoing.get(page_node.id, []):
            node = self.graph.nodes.get(target_id)
            if node and node.type == NodeType.ACTION:
                actions.append(node)
        return actions

    # ========== Test Case Query Methods ==========

    def find_test_cases_by_jira_tag(self, jira_tag: str) -> List[Node]:
        if not jira_tag.startswith("@"):
            jira_tag = f"@{jira_tag}"

        node_ids = self.indices.get_by_jira_tag(jira_tag)
        return [
            self.graph.nodes[nid]
            for nid in node_ids
            if nid in self.graph.nodes and self.graph.nodes[nid].type == NodeType.TEST_CASE
        ]

    def find_test_cases_using_api(self, api_node: Node) -> List[Node]:
        return self._collect_test_case_callers(api_node.id)

    def find_test_cases_using_workflow(self, workflow_node: Node) -> List[Node]:
        test_cases = self._collect_test_case_callers(workflow_node.id)
        for scenario in self.find_scenarios_in_workflow(workflow_node):
            test_cases.extend(self._collect_test_case_callers(scenario.id))
        return self._dedupe_nodes(test_cases)

    def find_test_cases_using_scenario(self, scenario_node: Node) -> List[Node]:
        return self._collect_test_case_callers(scenario_node.id)

    def find_test_cases_using_page(self, page_node: Node) -> List[Node]:
        test_cases = self._collect_test_case_callers(page_node.id)
        for action in self.find_actions_in_page(page_node):
            test_cases.extend(self._collect_test_case_callers(action.id))
        return self._dedupe_nodes(test_cases)

    # ========== Usage Statistics Methods ==========

    def get_usage_stats(
        self,
        node: Node,
        include_test_cases: bool = True,
        test_case_limit: Optional[int] = None,
    ) -> Dict:
        used_by = self._collect_test_case_callers(node.id)

        stats = {
            "node_id": node.id,
            "node_type": node.type.value,
            "node_name": node.name,
            "usage_count": len(used_by),
            "used_by_test_cases": self._test_case_payloads(used_by, test_case_limit) if include_test_cases else [],
            "direct_dependencies": self._direct_dependencies(node),
        }
        if test_case_limit is not None and len(used_by) > max(test_case_limit, 0):
            stats["used_by_test_cases_truncated"] = True
            stats["used_by_test_cases_total"] = len(used_by)

        if node.type == NodeType.WORKFLOW:
            scenarios = self.find_scenarios_in_workflow(node)
            stats["scenarios_count"] = len(scenarios)
            stats["scenarios"] = [
                {
                    "id": s.id,
                    "tag": s.metadata.additional_data.get("scenario_tag"),
                    "usage_count": self.get_usage_count(s),
                }
                for s in scenarios
            ]
        elif node.type == NodeType.PAGE:
            actions = self.find_actions_in_page(node)
            stats["actions_count"] = len(actions)
            stats["actions"] = [
                {
                    "id": a.id,
                    "tag": a.metadata.additional_data.get("action_tag"),
                    "usage_count": self.get_usage_count(a),
                }
                for a in actions
            ]

        return stats

    def get_most_used_apis(self, limit: int = 10) -> List[Tuple[Node, int]]:
        self._build_usage_index()
        api_usage = []
        for node in self._nodes_of_type(NodeType.API):
            api_usage.append((node, self.get_usage_count(node)))
        api_usage.sort(key=lambda x: x[1], reverse=True)
        return api_usage[:limit]

    def get_most_used_workflows(self, limit: int = 10) -> List[Tuple[Node, int]]:
        self._build_usage_index()
        workflow_usage = []
        for node in self._nodes_of_type(NodeType.WORKFLOW):
            workflow_usage.append((node, self.get_usage_count(node)))
        workflow_usage.sort(key=lambda x: x[1], reverse=True)
        return workflow_usage[:limit]

    def get_unused_components(self) -> Dict[str, List[Node]]:
        self._build_usage_index()
        unused = {
            "workflows": [],
            "pages": [],
            "apis": [],
            "scenarios": [],
            "actions": [],
            "javascript": [],
            "js_functions": [],
        }

        for node in self.graph.nodes.values():
            if node.type == NodeType.TEST_CASE:
                continue
            if self.get_usage_count(node):
                continue

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
            elif node.type == NodeType.JAVASCRIPT:
                unused["javascript"].append(node)
            elif node.type == NodeType.JS_FUNCTION:
                unused["js_functions"].append(node)

        return unused

    def get_api_stats(self, keyword: Optional[str] = None) -> Dict[str, Any]:
        """Get API statistics for the graph."""
        api_nodes = list(self._nodes_of_type(NodeType.API))
        
        if keyword:
            keyword_lower = keyword.lower()
            api_nodes = [
                n for n in api_nodes 
                if keyword_lower in n.name.lower() or 
                   keyword_lower in n.metadata.additional_data.get('path', '').lower()
            ]
            
        domain_stats = {}
        for node in api_nodes:
            meta = node.metadata.additional_data
            domain = str(meta.get('domain', '') or meta.get('base_url', '') or "Unknown")
            domain_stats[domain] = domain_stats.get(domain, 0) + 1
            
        sorted_apis = sorted(
            api_nodes, 
            key=lambda n: (str(n.metadata.additional_data.get('base_url', '')), str(n.metadata.additional_data.get('path', '')))
        )
        
        return {
            "total_count": len(api_nodes),
            "domain_breakdown": domain_stats,
            "results": [
                {
                    "id": n.id,
                    "method": n.metadata.additional_data.get('http_method'),
                    "url": n.name,
                    "path": n.metadata.additional_data.get('path'),
                    "domain": str(n.metadata.additional_data.get('domain', '') or n.metadata.additional_data.get('base_url', ''))
                }
                for n in sorted_apis
            ]
        }

    def get_page_stats(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """Get Page statistics for the graph."""
        page_nodes = list(self._nodes_of_type(NodeType.PAGE))
        
        domain_stats = {}
        for node in page_nodes:
            biz_domain = node.metadata.additional_data.get('feature', 'Unclassified')
            domain_stats[biz_domain] = domain_stats.get(biz_domain, 0) + 1
            
        if domain:
            target = domain.lower()
            page_nodes = [
                n for n in page_nodes 
                if n.metadata.additional_data.get('feature', '').lower() == target
            ]

        return {
            "total_count": len(page_nodes),
            "domain_breakdown": domain_stats,
            "results": [
                {
                    "id": n.id,
                    "name": n.name,
                    "file_path": n.metadata.file_path,
                    "business_domain": n.metadata.additional_data.get('feature')
                }
                for n in page_nodes
            ]
        }
