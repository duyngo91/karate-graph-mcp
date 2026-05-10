"""Database tracking utilities for AI context and impact analysis."""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from karate_graph_analyzer.graph.graph_query import GraphQuery
from karate_graph_analyzer.models import DependencyGraph, NodeType, Project, Scenario, Step
from karate_graph_analyzer.parser.extractors.call_read_extractor import CallReadExtractor
from karate_graph_analyzer.parser.extractors.database_extractor import DatabaseExtractor
from karate_graph_analyzer.parser.feature_parser import FeatureFileParser
from karate_graph_analyzer.utils.db_dialect import DbDialectDetector
from karate_graph_analyzer.utils.scan_filters import is_excluded_path


class DbTrackingService:
    """Build AI-ready DB indexes and traces from graph + feature files."""

    DEFAULT_VISIBLE_LINK_STATUSES = ("linked", "orphan")
    DEMO_MARKERS = ("example", "examples", "demo", "sample", "fixture")

    ASSERTION_PATTERN = re.compile(r"\b(status|match|assert)\b", re.IGNORECASE)
    DEF_PATTERN = re.compile(r"\bdef\s+([A-Za-z_][\w]*)\s*=\s*(.+)$")
    SET_PATTERN = re.compile(r"\bset\s+([A-Za-z_][\w.]*)\s*=\s*(.+)$")
    SQL_OPERATION_PATTERN = re.compile(
        r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|UPSERT)\b",
        re.IGNORECASE,
    )
    SQL_TABLE_PATTERN = re.compile(
        r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+[`\"\[]?([A-Za-z_][A-Za-z0-9_.]*)[`\"\]]?",
        re.IGNORECASE,
    )
    SQL_COLUMN_PATTERN = re.compile(
        r"\bSELECT\s+(.+?)\s+FROM\b",
        re.IGNORECASE,
    )
    TEMPLATE_VAR_PATTERN = re.compile(r"#\(\s*([A-Za-z_][\w]*)\s*\)")

    def __init__(self, project: Project, graph: Optional[DependencyGraph] = None) -> None:
        self.project = project
        self.graph = graph
        self.root = Path(project.root_path)
        self.parser = FeatureFileParser(project.parser_config)
        self.call_read_extractor = CallReadExtractor(project.parser_config)
        self.db_extractor = DatabaseExtractor(project.parser_config)
        self._feature_cache: Optional[List[Dict[str, Any]]] = None

    def db_query_index(
        self,
        query: Optional[str] = None,
        limit: int = 100,
        include_components: bool = True,
        link_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        entries = self._db_nodes_from_graph(include_components=include_components)
        if query:
            terms = self._terms(query)
            entries = [item for item in entries if self._entry_matches(item, terms)]
        entries = self._filter_by_link_status(entries, link_status)

        return {
            "queries": entries[:limit],
            "count": min(len(entries), limit),
            "total_available": len(entries),
            "link_status_summary": self._link_status_summary(entries),
            "default_visible_link_statuses": list(self.DEFAULT_VISIBLE_LINK_STATUSES),
        }

    def search_db_usage(
        self,
        query: str,
        limit: int = 100,
        link_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        terms = self._terms(query)
        entries = [item for item in self._db_nodes_from_graph(include_components=True) if self._entry_matches(item, terms)]
        entries = self._filter_by_link_status(entries, link_status)
        entries.sort(key=lambda item: (item.get("usage_count", 0), item.get("risk_score", 0.0)), reverse=True)
        return {
            "results": entries[:limit],
            "count": min(len(entries), limit),
            "total_available": len(entries),
            "link_status_summary": self._link_status_summary(entries),
            "default_visible_link_statuses": list(self.DEFAULT_VISIBLE_LINK_STATUSES),
        }

    def db_data_flow_trace(
        self,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        traces = []
        for feature, scenario in self._matching_scenarios(
            feature_path, scenario_tag, scenario_name, node_id, limit
        ):
            all_steps = feature["background_steps"] + scenario.steps
            definitions = self._defined_variables(all_steps)
            db_steps = [step for step in all_steps if self._is_db_relevant_step(step.text)]
            db_vars = self._db_variable_names(definitions, db_steps)
            variable_traces = []
            for definition in definitions:
                if not self._variable_is_db_related(definition, db_vars, all_steps):
                    continue
                variable_traces.append(
                    {
                        **definition,
                        "used_at": self._variable_usages(
                            definition["name"], all_steps, definition["line_number"]
                        ),
                    }
                )

            db_calls = [self._db_call_payload(feature["file_path"], step) for step in db_steps]
            assertions = [
                self._db_assertion_payload(feature, scenario, step, db_vars)
                for step in scenario.steps
                if self._is_assertion_step(step.text) and self._is_db_assertion(step.text, db_vars)
            ]

            traces.append(
                {
                    "feature_file": feature["file_path"],
                    "scenario_name": scenario.name,
                    "line_number": scenario.line_number,
                    "tags": scenario.tags,
                    "jira_tags": scenario.jira_tags,
                    "db_variables": variable_traces,
                    "db_calls": db_calls,
                    "db_assertions": assertions,
                    "db_query_signatures": self._db_query_signatures(db_steps),
                }
            )

        return {
            "traces": traces[:limit],
            "count": min(len(traces), limit),
            "total_available": len(traces),
        }

    def db_assertion_map(
        self,
        query: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        assertions: List[Dict[str, Any]] = []
        total_available = 0
        terms = self._terms(query) if query else []
        for feature, scenario in self._iter_scenarios():
            all_steps = feature["background_steps"] + scenario.steps
            definitions = self._defined_variables(all_steps)
            db_steps = [step for step in all_steps if self._is_db_relevant_step(step.text)]
            if not db_steps:
                continue
            db_vars = self._db_variable_names(definitions, db_steps)
            query_signatures = self._db_query_signatures(db_steps)
            for step in scenario.steps:
                if not self._is_assertion_step(step.text):
                    continue
                if not self._is_db_assertion(step.text, db_vars):
                    continue
                payload = {
                    "feature_file": feature["file_path"],
                    "scenario_name": scenario.name,
                    "line_number": step.line_number,
                    "jira_tags": scenario.jira_tags,
                    "tags": scenario.tags,
                    "assertion_type": self._assertion_type(step.text),
                    "target": self._assertion_target(step.text),
                    "step": step.text,
                    "db_variables": sorted(db_vars),
                    "db_query_signatures": query_signatures,
                }
                if terms and not self._entry_matches(payload, terms):
                    continue
                total_available += 1
                if len(assertions) < limit:
                    assertions.append(payload)

        return {
            "assertions": assertions,
            "count": len(assertions),
            "total_available": total_available,
        }

    def db_impact_preview(
        self,
        changed_entities: List[str],
        limit: int = 50,
    ) -> Dict[str, Any]:
        if not self.graph:
            return {
                "results": [],
                "count": 0,
                "total_available": 0,
                "warning": "Project graph is not available; analyze the project first.",
            }

        query_api = GraphQuery(self.graph)
        query_api._build_usage_index()
        terms = [term.lower() for term in changed_entities if term and term.strip()]
        impacted: Dict[str, Dict[str, Any]] = {}
        matched_nodes: List[Dict[str, Any]] = []

        for node in self.graph.nodes.values():
            if node.type != NodeType.DATABASE:
                continue
            matched_entities = self._db_node_matched_entities(node, terms)
            if not matched_entities:
                continue

            stats = query_api.get_usage_stats(node, test_case_limit=100)
            dialect_info = self._dialect_context(node)
            kind = self._db_node_kind(node, dialect_info)
            link_status, link_status_reason = self._db_link_status(node, kind, stats)
            matched_nodes.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "kind": kind,
                    "link_status": link_status,
                    "link_status_reason": link_status_reason,
                    "file_path": node.metadata.file_path,
                    "line_number": node.metadata.line_number,
                    "operation": node.metadata.additional_data.get("operation"),
                    "table": node.metadata.additional_data.get("table"),
                    "database": node.metadata.additional_data.get("database"),
                    "host": node.metadata.additional_data.get("host"),
                    "db_type": dialect_info.get("db_type"),
                    "dialect": dialect_info.get("dialect"),
                    "provider": dialect_info.get("provider"),
                    "entity_type": dialect_info.get("entity_type"),
                    "entity_name": dialect_info.get("entity_name"),
                    "usage_count": stats.get("usage_count", 0),
                    "matched_entities": matched_entities,
                }
            )

            for test_case in stats.get("used_by_test_cases", []):
                tc_id = test_case.get("id")
                if not tc_id:
                    continue
                item = impacted.setdefault(
                    tc_id,
                    {
                        "id": tc_id,
                        "name": test_case.get("name"),
                        "jira_tags": test_case.get("jira_tags", []),
                        "test_case_id": test_case.get("test_case_id"),
                        "matched_nodes": [],
                        "trigger_count": 0,
                        "matched_entities": [],
                    },
                )
                item["trigger_count"] += 1
                item["matched_entities"].extend(matched_entities)
                item["matched_nodes"].append(
                    {
                        "id": node.id,
                        "name": node.name,
                        "operation": node.metadata.additional_data.get("operation"),
                        "table": node.metadata.additional_data.get("table"),
                        "db_type": dialect_info.get("db_type"),
                        "dialect": dialect_info.get("dialect"),
                        "provider": dialect_info.get("provider"),
                        "entity_type": dialect_info.get("entity_type"),
                        "entity_name": dialect_info.get("entity_name"),
                        "matched_entities": matched_entities,
                    }
                )

        results = list(impacted.values())
        for item in results:
            item["matched_entities"] = list(dict.fromkeys(item["matched_entities"]))
        results.sort(key=lambda item: item["trigger_count"], reverse=True)
        matched_nodes.sort(key=lambda item: item.get("usage_count", 0), reverse=True)
        return {
            "results": results[:limit],
            "matched_db_nodes": matched_nodes[:limit],
            "count": min(len(results), limit),
            "total_available": len(results),
        }

    def _db_nodes_from_graph(self, include_components: bool) -> List[Dict[str, Any]]:
        if not self.graph:
            return []
        query_api = GraphQuery(self.graph)
        query_api._build_usage_index()
        entries: List[Dict[str, Any]] = []

        for node in self.graph.nodes.values():
            if node.type != NodeType.DATABASE:
                continue
            payload = self._db_node_payload(node, query_api)
            if payload["kind"] == "component" and not include_components:
                continue
            entries.append(payload)

        entries.sort(
            key=lambda item: (
                item.get("kind") == "query",
                item.get("usage_count", 0),
                item.get("risk_score", 0.0),
                item.get("name", ""),
            ),
            reverse=True,
        )
        return entries

    def _db_node_payload(self, node: Any, query_api: GraphQuery) -> Dict[str, Any]:
        data = node.metadata.additional_data or {}
        operation = data.get("operation")
        table = data.get("table")
        database = data.get("database")
        host = data.get("host")
        dialect_info = self._dialect_context(node)
        dialect = dialect_info.get("dialect")
        entity_name = dialect_info.get("entity_name")
        kind = self._db_node_kind(node, dialect_info)
        store_type = self._store_type(data, node.name, dialect_info)
        risk = self._risk_level(operation, node.name)
        stats = query_api.get_usage_stats(node, test_case_limit=25)
        link_status, link_status_reason = self._db_link_status(node, kind, stats)

        return {
            "id": node.id,
            "kind": kind,
            "link_status": link_status,
            "link_status_reason": link_status_reason,
            "name": node.name,
            "operation": operation,
            "table": table,
            "database": database,
            "host": host,
            "store_type": store_type,
            "db_type": dialect_info.get("db_type"),
            "dialect": dialect,
            "provider": dialect_info.get("provider"),
            "dialect_confidence": dialect_info.get("dialect_confidence"),
            "dialect_signals": dialect_info.get("dialect_signals", []),
            "entity_type": dialect_info.get("entity_type"),
            "entity_name": entity_name,
            "risk_level": risk["level"],
            "risk_score": risk["score"],
            "file_path": node.metadata.file_path,
            "line_number": node.metadata.line_number,
            "scenario_name": data.get("scenario_name"),
            "scenario_tags": data.get("scenario_tags", []),
            "usage_count": stats.get("usage_count", 0),
            "used_by_test_cases": stats.get("used_by_test_cases", []),
            "direct_dependencies": stats.get("direct_dependencies", []),
        }

    def _db_node_kind(self, node: Any, dialect_info: Dict[str, Any]) -> str:
        data = node.metadata.additional_data or {}
        dialect = dialect_info.get("dialect") or "unknown"
        entity_name = dialect_info.get("entity_name")
        if any(
            [
                data.get("operation"),
                data.get("table"),
                data.get("database"),
                data.get("host"),
                entity_name,
            ]
        ) or dialect != "unknown":
            return "query"
        return "component"

    def _db_link_status(
        self,
        node: Any,
        kind: str,
        stats: Dict[str, Any],
    ) -> tuple[str, str]:
        if stats.get("used_by_test_cases"):
            return "linked", "DB entry is reachable from at least one terminal test case."
        if kind == "component":
            return "component", "DB feature/helper component; keep it for structure and reuse context."
        if self._is_demo_db_node(node):
            return "demo", "DB entry comes from an example/demo flow and is not counted as execution impact."
        return "orphan", "DB query has no upstream terminal test case; inspect call/read linkage or test coverage."

    def _is_demo_db_node(self, node: Any) -> bool:
        text = " ".join(self._node_context_terms(node)).lower()
        return any(marker in text for marker in self.DEMO_MARKERS)

    def _node_context_terms(self, node: Any, max_depth: int = 2) -> List[str]:
        terms = [
            node.name,
            str(node.metadata.file_path or ""),
            " ".join(node.tags or []),
            " ".join(node.metadata.jira_tags or []),
        ]
        data = node.metadata.additional_data or {}
        terms.extend(
            [
                str(data.get("scenario_name", "")),
                " ".join(data.get("scenario_tags", []) or []),
                str(data.get("feature", "")),
            ]
        )
        if not self.graph:
            return terms

        seen = {node.id}
        frontier = [node.id]
        incoming = self._incoming_edge_map()
        for _ in range(max_depth):
            next_frontier = []
            for target_id in frontier:
                for parent_id in incoming.get(target_id, []):
                    if parent_id in seen:
                        continue
                    seen.add(parent_id)
                    parent = self.graph.nodes.get(parent_id)
                    if not parent:
                        continue
                    terms.append(parent.name)
                    terms.append(str(parent.metadata.file_path or ""))
                    terms.extend(parent.tags or [])
                    terms.extend(parent.metadata.jira_tags or [])
                    parent_data = parent.metadata.additional_data or {}
                    terms.append(str(parent_data.get("scenario_name", "")))
                    terms.extend(parent_data.get("scenario_tags", []) or [])
                    terms.append(str(parent_data.get("workflow_path", "")))
                    next_frontier.append(parent_id)
            frontier = next_frontier
            if not frontier:
                break
        return terms

    def _incoming_edge_map(self) -> Dict[str, List[str]]:
        if hasattr(self, "_incoming_edges"):
            return self._incoming_edges
        incoming: Dict[str, List[str]] = {}
        if self.graph:
            for edge in self.graph.edges.values():
                incoming.setdefault(edge.to_node, []).append(edge.from_node)
        self._incoming_edges = incoming
        return incoming

    def _filter_by_link_status(
        self,
        entries: List[Dict[str, Any]],
        link_status: Optional[str],
    ) -> List[Dict[str, Any]]:
        statuses = self._normalize_link_status_filter(link_status)
        if not statuses:
            return entries
        return [entry for entry in entries if entry.get("link_status") in statuses]

    def _normalize_link_status_filter(self, link_status: Optional[str]) -> Set[str]:
        if not link_status:
            return set()
        if link_status.lower() in {"default", "impact"}:
            return set(self.DEFAULT_VISIBLE_LINK_STATUSES)
        return {
            status.strip().lower()
            for status in link_status.split(",")
            if status.strip()
        }

    def _link_status_summary(self, entries: List[Dict[str, Any]]) -> Dict[str, int]:
        summary = {status: 0 for status in ["linked", "orphan", "component", "demo"]}
        for entry in entries:
            status = entry.get("link_status") or "unknown"
            summary[status] = summary.get(status, 0) + 1
        return summary

    def _dialect_context(self, node: Any) -> Dict[str, Any]:
        data = node.metadata.additional_data or {}
        text = " ".join(
            [
                node.name,
                str(data.get("operation", "")),
                str(data.get("table", "")),
                str(data.get("database", "")),
                str(data.get("host", "")),
                str(data.get("collection", "")),
                str(data.get("key", "")),
                str(data.get("index", "")),
                str(data.get("keyspace", "")),
            ]
        )
        return DbDialectDetector.detect(text, data)

    def _store_type(
        self,
        data: Dict[str, Any],
        fallback: str,
        dialect_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        dialect_info = dialect_info or DbDialectDetector.detect(fallback, data)
        db_type = dialect_info.get("db_type")
        if db_type and db_type != "unknown":
            return db_type
        text = " ".join(
            [
                str(data.get("operation", "")),
                str(data.get("host", "")),
                str(data.get("database", "")),
                str(data.get("table", "")),
                fallback,
            ]
        ).lower()
        if any(keyword in text for keyword in ["mongodb", "collection", "findone", "insertone"]):
            return "document"
        if any(keyword in text for keyword in ["redis", "hget", "hset", "set ", "get ", "del "]):
            return "key-value"
        if any(keyword in text for keyword in ["elasticsearch", "opensearch", "index", "_search"]):
            return "search"
        return "relational"

    def _risk_level(self, operation: Optional[str], fallback: str) -> Dict[str, Any]:
        op = (operation or "").upper()
        if not op:
            # If operation is unavailable, treat as medium and let callers inspect details.
            return {"level": "medium", "score": 0.5}
        if op in {
            "SELECT", "SHOW", "DESCRIBE", "EXPLAIN", "FIND", "FINDONE", "GET",
            "HGET", "MGET", "QUERY", "SCAN", "GETITEM", "SEARCH", "AGGREGATE", "MATCH",
        }:
            return {"level": "read", "score": 0.2}
        if op in {
            "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "INSERTONE", "UPDATEONE",
            "DELETEONE", "SET", "HSET", "DEL", "PUTITEM", "UPDATEITEM", "DELETEITEM", "INDEX",
        }:
            return {"level": "write", "score": 0.8}
        if op in {"CREATE", "DROP", "ALTER", "TRUNCATE", "CREATEINDEX", "DROPINDEX"}:
            return {"level": "ddl", "score": 1.0}
        if "DROP" in fallback.upper() or "TRUNCATE" in fallback.upper():
            return {"level": "ddl", "score": 1.0}
        return {"level": "medium", "score": 0.5}

    def _db_node_matched_entities(self, node: Any, entities: List[str]) -> List[str]:
        if not entities:
            return []
        payload = {
            "name": node.name,
            "file_path": node.metadata.file_path,
            "additional_data": node.metadata.additional_data,
            "dialect_context": self._dialect_context(node),
        }
        return [entity for entity in entities if self._entry_matches(payload, [entity])]

    def _defined_variables(self, steps: List[Step]) -> List[Dict[str, Any]]:
        variables = []
        for step in steps:
            for pattern in [self.DEF_PATTERN, self.SET_PATTERN]:
                match = pattern.search(step.text)
                if not match:
                    continue
                name = match.group(1).split(".")[0]
                expression = match.group(2).strip()
                variables.append(
                    {
                        "name": name,
                        "line_number": step.line_number,
                        "expression": expression,
                        "is_sql": self._looks_like_sql(expression),
                        "dialect_context": DbDialectDetector.detect(expression),
                        "template_variables": self._template_variables(expression),
                    }
                )
        return variables

    def _db_variable_names(self, definitions: List[Dict[str, Any]], steps: List[Step]) -> Set[str]:
        names: Set[str] = set()
        for definition in definitions:
            expression = definition["expression"]
            if definition["is_sql"] or self._is_db_call_expression(expression):
                names.add(definition["name"])
            names.update(definition["template_variables"])

        for step in steps:
            names.update(self._template_variables(step.text))
        return names

    def _variable_is_db_related(
        self,
        definition: Dict[str, Any],
        db_variable_names: Set[str],
        steps: List[Step],
    ) -> bool:
        name = definition["name"]
        if name in db_variable_names:
            return True
        usages = self._variable_usages(name, steps, definition["line_number"])
        return any(item.get("is_db_context") for item in usages)

    def _variable_usages(self, name: str, steps: List[Step], definition_line: int) -> List[Dict[str, Any]]:
        pattern = re.compile(rf"\b{re.escape(name)}\b")
        usages = []
        for step in steps:
            if step.line_number == definition_line:
                continue
            if not pattern.search(step.text):
                continue
            usages.append(
                {
                    "line_number": step.line_number,
                    "step": step.text,
                    "is_db_context": self._is_db_relevant_step(step.text),
                }
            )
        return usages

    def _db_call_payload(self, current_feature_file: str, step: Step) -> Dict[str, Any]:
        dependencies = self.call_read_extractor.extract(step.text, step.line_number)
        resolved_file = None
        target = None
        scenario_tag = None
        for dep in dependencies:
            params = dep.parameters or {}
            target = dep.target
            scenario_tag = params.get("scenario_tag")
            resolved_file = self._resolve_call_target_file(current_feature_file, dep.target, params)
            if self._is_db_path(dep.target) or (resolved_file and self._is_db_path(resolved_file)):
                break

        return {
            "line_number": step.line_number,
            "step": step.text,
            "target": target,
            "scenario_tag": scenario_tag,
            "resolved_file": resolved_file,
            "template_variables": self._template_variables(step.text),
            "query_details": self._query_details_from_text(step.text),
        }

    def _db_query_signatures(self, steps: List[Step]) -> List[Dict[str, Any]]:
        signatures: List[Dict[str, Any]] = []
        for step in steps:
            if not self.db_extractor.can_extract(step.text):
                continue
            deps = self.db_extractor.extract(step.text, step.line_number)
            for dep in deps:
                item = {
                    "line_number": step.line_number,
                    "signature": dep.target,
                    "operation": dep.parameters.get("operation"),
                    "table": dep.parameters.get("table"),
                    "database": dep.parameters.get("database"),
                    "host": dep.parameters.get("host"),
                    "db_type": dep.parameters.get("db_type"),
                    "dialect": dep.parameters.get("dialect"),
                    "provider": dep.parameters.get("provider"),
                    "entity_type": dep.parameters.get("entity_type"),
                    "entity_name": dep.parameters.get("entity_name"),
                }
                if item not in signatures:
                    signatures.append(item)
        return signatures

    def _db_assertion_payload(
        self,
        feature: Dict[str, Any],
        scenario: Scenario,
        step: Step,
        db_vars: Set[str],
    ) -> Dict[str, Any]:
        return {
            "feature_file": feature["file_path"],
            "scenario_name": scenario.name,
            "line_number": step.line_number,
            "step": step.text,
            "assertion_type": self._assertion_type(step.text),
            "target": self._assertion_target(step.text),
            "db_variables": [name for name in sorted(db_vars) if re.search(rf"\b{re.escape(name)}\b", step.text)],
        }

    def _query_details_from_text(self, text: str) -> Dict[str, Any]:
        operation_match = self.SQL_OPERATION_PATTERN.search(text)
        table_matches = self.SQL_TABLE_PATTERN.findall(text)
        columns_match = self.SQL_COLUMN_PATTERN.search(text)
        columns = []
        if columns_match:
            raw = columns_match.group(1).strip()
            if raw != "*":
                columns = [item.strip() for item in raw.split(",") if item.strip()]
        return {
            "operation": operation_match.group(1).upper() if operation_match else None,
            "tables": sorted(set(table_matches)),
            "columns": columns,
            **DbDialectDetector.detect(text),
        }

    def _is_db_assertion(self, step_text: str, db_vars: Set[str]) -> bool:
        if any(re.search(rf"\b{re.escape(name)}\b", step_text) for name in db_vars):
            return True
        lower = step_text.lower()
        return any(keyword in lower for keyword in ["result[", "row[", "sql", "query"])

    def _is_db_relevant_step(self, step_text: str) -> bool:
        return (
            self.db_extractor.can_extract(step_text)
            or self._is_db_call_step(step_text)
            or self._is_db_call_expression(step_text)
            or DbDialectDetector.detect(step_text).get("dialect") != "unknown"
        )

    def _is_db_call_step(self, step_text: str) -> bool:
        lower = step_text.lower().replace("\\", "/")
        return (
            "execute_query" in lower
            or "classpath:db/" in lower
            or "classpath:common/db/" in lower
            or "/db/" in lower
            or "jdbc:" in lower
        )

    def _is_db_call_expression(self, text: str) -> bool:
        lower = text.lower().replace("\\", "/")
        return "call read(" in lower and self._is_db_call_step(lower)

    def _is_db_path(self, path_text: Optional[str]) -> bool:
        if not path_text:
            return False
        lower = str(path_text).lower().replace("\\", "/")
        return "/db/" in lower or lower.startswith("db/") or "common/db/" in lower

    def _looks_like_sql(self, text: str) -> bool:
        return bool(self.SQL_OPERATION_PATTERN.search(text) and self.SQL_TABLE_PATTERN.search(text))

    def _template_variables(self, text: str) -> List[str]:
        return self.TEMPLATE_VAR_PATTERN.findall(text)

    def _assertion_type(self, text: str) -> str:
        lower = text.lower()
        if re.search(r"\bstatus\b", lower):
            return "status"
        if re.search(r"\bmatch\b", lower):
            return "match"
        if re.search(r"\bassert\b", lower):
            return "assert"
        return "unknown"

    def _assertion_target(self, text: str) -> Optional[str]:
        match = re.search(r"\b(?:match|assert)\s+(.+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.search(r"\bstatus\s+(\d+|[A-Za-z_][\w.]*)", text, re.IGNORECASE)
        return match.group(1) if match else None

    def _is_assertion_step(self, text: str) -> bool:
        return bool(self.ASSERTION_PATTERN.search(text))

    def _resolve_call_target_file(
        self,
        current_feature_file: str,
        target: str,
        params: Dict[str, Any],
    ) -> Optional[str]:
        raw = params.get("physical_path") or target
        if not raw or "${" in str(raw):
            return None
        raw = str(raw).replace("\\", "/")
        if raw.startswith("classpath:"):
            raw = raw.replace("classpath:", "").lstrip("/")

        candidates = [
            Path(raw),
            Path(current_feature_file).parent / raw,
            self.root / raw,
            self.root / "src/test/java" / raw,
            self.root / "src/test/resources" / raw,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve())
        return None

    def _feature_asts(self) -> List[Dict[str, Any]]:
        if self._feature_cache is not None:
            return self._feature_cache

        features: List[Dict[str, Any]] = []
        for file_path in self._feature_files():
            try:
                ast = self.parser.parse_file(str(file_path))
            except Exception:
                continue
            features.append(
                {
                    "file_path": str(file_path),
                    "feature_name": ast.feature_name,
                    "background_steps": ast.background_steps,
                    "scenarios": ast.scenarios,
                }
            )
        self._feature_cache = features
        return features

    def _iter_feature_asts(self) -> Iterable[Dict[str, Any]]:
        if self._feature_cache is not None:
            yield from self._feature_cache
            return

        files = self._feature_files()
        threshold = getattr(
            self.project.parser_config,
            "ai_context_cache_feature_threshold",
            5000,
        )
        if threshold <= 0 or len(files) <= threshold:
            yield from self._feature_asts()
            return

        for file_path in files:
            try:
                ast = self.parser.parse_file(str(file_path))
            except Exception:
                continue
            yield {
                "file_path": str(file_path),
                "feature_name": ast.feature_name,
                "background_steps": ast.background_steps,
                "scenarios": ast.scenarios,
            }

    def _feature_files(self) -> List[Path]:
        files: List[Path] = []
        for pattern in self.project.feature_file_patterns or ["**/*.feature"]:
            for path in self.root.glob(pattern):
                if path.is_file() and not is_excluded_path(path, self.project.parser_config):
                    files.append(path)
        return sorted({path.resolve() for path in files})

    def _iter_scenarios(self) -> Iterable[tuple[Dict[str, Any], Scenario]]:
        for feature in self._iter_feature_asts():
            for scenario in feature["scenarios"]:
                yield feature, scenario

    def _matching_scenarios(
        self,
        feature_path: Optional[str],
        scenario_tag: Optional[str],
        scenario_name: Optional[str],
        node_id: Optional[str],
        limit: Optional[int] = None,
    ) -> List[tuple[Dict[str, Any], Scenario]]:
        node_filter = self._node_filter(node_id)
        matches = []
        for feature, scenario in self._iter_scenarios():
            if node_filter and not self._matches_node_filter(feature, scenario, node_filter):
                continue
            if feature_path and not self._path_matches(feature["file_path"], feature_path):
                continue
            if scenario_tag and not self._tag_matches(scenario.tags + scenario.jira_tags, scenario_tag):
                continue
            if scenario_name and scenario_name.lower() not in scenario.name.lower():
                continue
            matches.append((feature, scenario))
            if limit is not None and len(matches) >= max(limit, 0):
                break
        return matches

    def _node_filter(self, node_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not node_id or not self.graph:
            return None
        node = self.graph.nodes.get(node_id)
        if not node:
            return None
        return {
            "file_path": node.metadata.file_path,
            "line_number": node.metadata.line_number,
            "name": node.name,
            "tags": node.metadata.jira_tags + node.tags,
        }

    def _matches_node_filter(
        self,
        feature: Dict[str, Any],
        scenario: Scenario,
        node_filter: Dict[str, Any],
    ) -> bool:
        file_path = node_filter.get("file_path")
        if file_path and not self._path_matches(feature["file_path"], file_path):
            return False
        line_number = node_filter.get("line_number")
        if line_number and scenario.line_number == line_number:
            return True
        name = node_filter.get("name") or ""
        return scenario.name in name or name in scenario.name

    def _entry_matches(self, entry: Dict[str, Any], terms: List[str]) -> bool:
        text = str(entry).lower()
        return all(term in text for term in terms)

    def _terms(self, query: str) -> List[str]:
        return [term for term in re.split(r"[^A-Za-z0-9_@.-]+", query.lower()) if term]

    def _path_matches(self, path: str, pattern: str) -> bool:
        return pattern.replace("\\", "/").lower() in path.replace("\\", "/").lower()

    def _tag_matches(self, tags: List[str], tag: str) -> bool:
        clean = tag if tag.startswith("@") else f"@{tag}"
        return clean in tags or tag in tags
