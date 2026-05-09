"""Feature-file understanding utilities for AI context."""

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from karate_graph_analyzer.graph.graph_query import GraphQuery
from karate_graph_analyzer.models import DependencyGraph, DependencyType, Project, Scenario, Step
from karate_graph_analyzer.parser.extractors.call_read_extractor import CallReadExtractor
from karate_graph_analyzer.parser.feature_parser import FeatureFileParser


class FeatureUnderstandingService:
    """Build AI-ready indexes and context packs from Karate feature files."""

    ASSERTION_PATTERN = re.compile(r"\b(status|match|assert)\b", re.IGNORECASE)
    DEF_PATTERN = re.compile(r"\bdef\s+([A-Za-z_][\w]*)\s*=\s*(.+)$")
    SET_PATTERN = re.compile(r"\bset\s+([A-Za-z_][\w.]*)\s*=\s*(.+)$")
    READ_PATTERN = re.compile(r"read\s*\(\s*['\"]([^'\"]+)['\"]")
    STATUS_CODE_PATTERN = re.compile(r"\bstatus\s+(\d{3})\b", re.IGNORECASE)
    API_TEMPLATE_PATTERN = re.compile(
        r"^\s*(given|and|when|then|\*)?\s*(method\s+\w+|status\s+\d{3})\s*$",
        re.IGNORECASE,
    )

    def __init__(self, project: Project, graph: Optional[DependencyGraph] = None) -> None:
        self.project = project
        self.graph = graph
        self.root = Path(project.root_path)
        self.parser = FeatureFileParser(project.parser_config)
        self.call_read_extractor = CallReadExtractor(project.parser_config)
        self._feature_cache: Optional[List[Dict[str, Any]]] = None

    def feature_intent_index(
        self,
        query: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        entries = [self._scenario_intent_entry(feature, scenario) for feature, scenario in self._iter_scenarios()]
        if query:
            terms = self._terms(query)
            entries = [entry for entry in entries if self._entry_matches(entry, terms)]
        return {
            "features": entries[:limit],
            "count": min(len(entries), limit),
            "total_available": len(entries),
        }

    def variable_data_flow_trace(
        self,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        traces = [
            self._scenario_variable_trace(feature, scenario)
            for feature, scenario in self._matching_scenarios(
                feature_path, scenario_tag, scenario_name, node_id
            )
        ]
        return {
            "traces": traces[:limit],
            "count": min(len(traces), limit),
            "total_available": len(traces),
        }

    def assertion_map(
        self,
        query: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        assertions = []
        for feature, scenario in self._iter_scenarios():
            for step in scenario.steps:
                if not self._is_assertion_step(step.text):
                    continue
                item = self._assertion_payload(feature, scenario, step)
                if not query or self._entry_matches(item, self._terms(query)):
                    assertions.append(item)

        return {
            "assertions": assertions[:limit],
            "count": min(len(assertions), limit),
            "total_available": len(assertions),
        }

    def call_read_deep_context(
        self,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        max_depth: int = 2,
        limit: int = 50,
    ) -> Dict[str, Any]:
        contexts = []
        for feature, scenario in self._matching_scenarios(
            feature_path, scenario_tag, scenario_name, node_id
        ):
            contexts.append(
                {
                    "feature_file": feature["file_path"],
                    "scenario_name": scenario.name,
                    "jira_tags": scenario.jira_tags,
                    "tags": scenario.tags,
                    "line_number": scenario.line_number,
                    "calls": self._call_chain(feature["file_path"], scenario, max_depth=max_depth),
                }
            )

        return {
            "contexts": contexts[:limit],
            "count": min(len(contexts), limit),
            "total_available": len(contexts),
        }

    def ai_feature_context_pack(
        self,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        max_call_depth: int = 2,
        limit: int = 20,
    ) -> Dict[str, Any]:
        packs = []
        for feature, scenario in self._matching_scenarios(
            feature_path, scenario_tag, scenario_name, node_id
        ):
            packs.append(
                {
                    "intent": self._scenario_intent_entry(feature, scenario),
                    "variable_data_flow": self._scenario_variable_trace(feature, scenario),
                    "assertions": [
                        self._assertion_payload(feature, scenario, step)
                        for step in scenario.steps
                        if self._is_assertion_step(step.text)
                    ],
                    "call_read_context": self._call_chain(
                        feature["file_path"],
                        scenario,
                        max_depth=max_call_depth,
                    ),
                    "graph_context": self._graph_context(feature["file_path"], scenario),
                }
            )

        return {
            "packs": packs[:limit],
            "count": min(len(packs), limit),
            "total_available": len(packs),
        }

    def feature_behavior_map(
        self,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        maps = []
        for feature, scenario in self._matching_scenarios(
            feature_path, scenario_tag, scenario_name, node_id
        ):
            all_steps = feature["background_steps"] + scenario.steps
            step_intents = [self._classify_step(step) for step in all_steps]
            maps.append(
                {
                    "feature_file": feature["file_path"],
                    "feature_name": feature["feature_name"],
                    "scenario_name": scenario.name,
                    "line_number": scenario.line_number,
                    "tags": scenario.tags,
                    "jira_tags": scenario.jira_tags,
                    "preconditions": self._precondition_steps(step_intents),
                    "actions": self._action_steps(step_intents),
                    "expectations": self._expectation_steps(step_intents),
                    "data_inputs": self._data_files_from_steps(all_steps),
                    "status_expectations": self._status_codes(all_steps),
                }
            )
        return {
            "behaviors": maps[:limit],
            "count": min(len(maps), limit),
            "total_available": len(maps),
        }

    def scenario_similarity_map(
        self,
        query: Optional[str] = None,
        limit: int = 50,
        top_k: int = 3,
    ) -> Dict[str, Any]:
        entries = [self._scenario_intent_entry(feature, scenario) for feature, scenario in self._iter_scenarios()]
        if query:
            terms = self._terms(query)
            anchors = [entry for entry in entries if self._entry_matches(entry, terms)]
        else:
            anchors = entries

        top_k = max(1, min(top_k, 10))
        rows = []
        for anchor in anchors:
            neighbors = self._similar_neighbors(anchor, entries, top_k)
            rows.append(
                {
                    "scenario": {
                        "feature_file": anchor["feature_file"],
                        "scenario_name": anchor["scenario_name"],
                        "tags": anchor["tags"],
                        "jira_tags": anchor["jira_tags"],
                        "intent_keywords": anchor["intent_keywords"],
                    },
                    "similar_scenarios": neighbors,
                }
            )

        return {
            "similarities": rows[:limit],
            "count": min(len(rows), limit),
            "total_available": len(rows),
        }

    def feature_reuse_advisor(
        self,
        min_group_size: int = 2,
        min_flow_length: int = 3,
        limit: int = 50,
        include_low_signal: bool = False,
    ) -> Dict[str, Any]:
        min_group_size = max(2, min(min_group_size, 50))
        min_flow_length = max(2, min(min_flow_length, 10))
        exact_groups = self._exact_duplicate_step_groups(min_group_size, include_low_signal)
        flow_groups = self._duplicate_flow_groups(
            min_group_size,
            min_flow_length,
            include_low_signal,
        )
        candidates = self._rank_reuse_candidates(exact_groups, flow_groups)

        return {
            "exact_duplicate_steps": exact_groups[:limit],
            "duplicate_flows": flow_groups[:limit],
            "refactor_candidates": candidates[:limit],
            "count": min(len(candidates), limit),
            "total_available": len(candidates),
            "settings": {
                "min_group_size": min_group_size,
                "min_flow_length": min_flow_length,
                "include_low_signal": include_low_signal,
            },
        }

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

    def _feature_files(self) -> List[Path]:
        files: List[Path] = []
        for pattern in self.project.feature_file_patterns or ["**/*.feature"]:
            files.extend(self.root.glob(pattern))
        return sorted({path.resolve() for path in files if path.is_file()})

    def _iter_scenarios(self) -> Iterable[tuple[Dict[str, Any], Scenario]]:
        for feature in self._feature_asts():
            for scenario in feature["scenarios"]:
                yield feature, scenario

    def _matching_scenarios(
        self,
        feature_path: Optional[str],
        scenario_tag: Optional[str],
        scenario_name: Optional[str],
        node_id: Optional[str],
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
        return matches

    def _scenario_intent_entry(self, feature: Dict[str, Any], scenario: Scenario) -> Dict[str, Any]:
        all_steps = feature["background_steps"] + scenario.steps
        step_intents = [self._classify_step(step) for step in all_steps]
        api_steps = [step.text for step in all_steps if self._classify_step(step)["intent"] == "request"]
        call_steps = [self._call_step_payload(feature["file_path"], step) for step in all_steps if "read(" in step.text]
        assertion_steps = [step.text for step in scenario.steps if self._is_assertion_step(step.text)]
        data_files = self._data_files_from_steps(all_steps)

        return {
            "feature_file": feature["file_path"],
            "feature_name": feature["feature_name"],
            "scenario_name": scenario.name,
            "scenario_type": scenario.type.value,
            "line_number": scenario.line_number,
            "tags": scenario.tags,
            "jira_tags": scenario.jira_tags,
            "step_count": len(scenario.steps),
            "intent_summary": self._intent_summary(scenario, api_steps, call_steps, assertion_steps, data_files),
            "intent_keywords": self._intent_keywords(scenario, step_intents, data_files),
            "step_intents": step_intents,
            "api_signals": api_steps,
            "call_reads": call_steps,
            "data_files": data_files,
            "assertions": assertion_steps,
            "examples": self._examples_payload(scenario),
        }

    def _scenario_variable_trace(self, feature: Dict[str, Any], scenario: Scenario) -> Dict[str, Any]:
        all_steps = feature["background_steps"] + scenario.steps
        variables = self._defined_variables(all_steps)
        for variable in variables:
            variable["used_at"] = self._variable_usages(variable["name"], all_steps, variable["line_number"])

        return {
            "feature_file": feature["file_path"],
            "scenario_name": scenario.name,
            "line_number": scenario.line_number,
            "tags": scenario.tags,
            "jira_tags": scenario.jira_tags,
            "variables": variables,
            "data_files": self._data_files_from_steps(all_steps),
            "config_references": self._config_references(all_steps),
        }

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
                        "source_type": self._source_type(expression),
                        "source_files": self.READ_PATTERN.findall(expression),
                    }
                )
        return variables

    def _variable_usages(self, name: str, steps: List[Step], definition_line: int) -> List[Dict[str, Any]]:
        usages = []
        pattern = re.compile(rf"\b{re.escape(name)}\b")
        for step in steps:
            if step.line_number == definition_line:
                continue
            if pattern.search(step.text):
                usages.append(
                    {
                        "line_number": step.line_number,
                        "step": step.text,
                        "intent": self._classify_step(step)["intent"],
                    }
                )
        return usages

    def _assertion_payload(self, feature: Dict[str, Any], scenario: Scenario, step: Step) -> Dict[str, Any]:
        return {
            "feature_file": feature["file_path"],
            "scenario_name": scenario.name,
            "jira_tags": scenario.jira_tags,
            "tags": scenario.tags,
            "line_number": step.line_number,
            "assertion_type": self._assertion_type(step.text),
            "target": self._assertion_target(step.text),
            "step": step.text,
        }

    def _call_chain(
        self,
        current_feature_file: str,
        scenario: Scenario,
        max_depth: int,
        visited: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        visited = visited or set()
        calls = []
        for step in scenario.steps:
            for dependency in self.call_read_extractor.extract(step.text, step.line_number):
                call = self._call_dependency_payload(current_feature_file, dependency, step)
                call_key = f"{call.get('resolved_file')}#{call.get('scenario_tag')}"
                if max_depth > 0 and call.get("resolved_file") and call_key not in visited:
                    visited.add(call_key)
                    call["target_scenarios"] = self._target_scenarios_for_call(call, max_depth, visited)
                calls.append(call)
        return calls

    def _target_scenarios_for_call(
        self,
        call: Dict[str, Any],
        max_depth: int,
        visited: Set[str],
    ) -> List[Dict[str, Any]]:
        target_file = call.get("resolved_file")
        if not target_file or not str(target_file).endswith(".feature"):
            return []

        feature = self._feature_by_path(target_file)
        if not feature:
            return []

        scenario_tag = call.get("scenario_tag")
        targets = [
            scenario for scenario in feature["scenarios"]
            if not scenario_tag or self._tag_matches(scenario.tags + scenario.jira_tags, scenario_tag)
        ]
        return [
            {
                "scenario_name": scenario.name,
                "line_number": scenario.line_number,
                "tags": scenario.tags,
                "jira_tags": scenario.jira_tags,
                "intent_summary": self._scenario_intent_entry(feature, scenario)["intent_summary"],
                "calls": self._call_chain(
                    feature["file_path"],
                    scenario,
                    max_depth=max_depth - 1,
                    visited=visited,
                ),
            }
            for scenario in targets
        ]

    def _call_step_payload(self, current_feature_file: str, step: Step) -> Dict[str, Any]:
        dependencies = self.call_read_extractor.extract(step.text, step.line_number)
        if not dependencies:
            return {"line_number": step.line_number, "step": step.text}
        return self._call_dependency_payload(current_feature_file, dependencies[0], step)

    def _call_dependency_payload(
        self,
        current_feature_file: str,
        dependency: Any,
        step: Step,
    ) -> Dict[str, Any]:
        params = dependency.parameters or {}
        resolved_file = self._resolve_call_target_file(current_feature_file, dependency.target, params)
        return {
            "line_number": step.line_number,
            "step": step.text,
            "dependency_type": dependency.type.value,
            "target": dependency.target,
            "resolved_file": resolved_file,
            "scenario_tag": params.get("scenario_tag"),
            "params": params.get("params"),
            "original_expression": params.get("original_expression"),
            "unresolved": params.get("unresolved", False),
            "reason": params.get("reason"),
        }

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

    def _feature_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        normalized = str(Path(path).resolve()).lower()
        for feature in self._feature_asts():
            if str(Path(feature["file_path"]).resolve()).lower() == normalized:
                return feature
        return None

    def _graph_context(self, feature_file: str, scenario: Scenario) -> Dict[str, Any]:
        if not self.graph:
            return {}
        node = self._graph_node_for_scenario(feature_file, scenario)
        if not node:
            return {}
        query = GraphQuery(self.graph)
        return {
            "node_id": node.id,
            "node_type": node.type.value,
            "node_name": node.name,
            "usage_stats": query.get_usage_stats(node),
            "direct_dependencies": query.get_usage_stats(node).get("direct_dependencies", []),
        }

    def _graph_node_for_scenario(self, feature_file: str, scenario: Scenario) -> Optional[Any]:
        if not self.graph:
            return None
        target_path = str(Path(feature_file).resolve()).lower()
        for node in self.graph.nodes.values():
            node_path = node.metadata.file_path
            if not node_path:
                continue
            if str(Path(node_path).resolve()).lower() != target_path:
                continue
            if node.metadata.line_number == scenario.line_number or scenario.name in node.name:
                return node
        return None

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

    def _classify_step(self, step: Step) -> Dict[str, Any]:
        text = step.text.lower()
        intent = "other"
        if "call " in text or "read(" in text or "callonce" in text:
            intent = "call-reuse"
        if any(word in text for word in ["login", "auth", "token", "jwt"]):
            intent = "auth"
        if re.search(r"\b(url|path|request|method)\b", text):
            intent = "request"
        if self._is_assertion_step(step.text):
            intent = "assertion"
        if re.search(r"\bdef\b|\bset\b|read\s*\(", text):
            intent = "data-prepare" if intent == "other" else intent
        if any(word in text for word in ["karate.log", "print ", "debug"]):
            intent = "debug"
        if any(word in text for word in ["sql", "jdbc", "database", "db."]):
            intent = "database"
        if any(word in text for word in ["click", "input", "navigate", "locator"]):
            intent = "ui"

        return {
            "line_number": step.line_number,
            "keyword": step.keyword,
            "intent": intent,
            "step": step.text,
        }

    def _intent_summary(
        self,
        scenario: Scenario,
        api_steps: List[str],
        call_steps: List[Dict[str, Any]],
        assertion_steps: List[str],
        data_files: List[str],
    ) -> str:
        parts = [f"Scenario '{scenario.name}'"]
        if api_steps:
            parts.append(f"drives {len(api_steps)} API step(s)")
        if call_steps:
            parts.append(f"reuses {len(call_steps)} call/read component(s)")
        if data_files:
            parts.append(f"loads data from {', '.join(data_files[:3])}")
        if assertion_steps:
            parts.append(f"validates {len(assertion_steps)} assertion/status step(s)")
        return "; ".join(parts) + "."

    def _intent_keywords(
        self,
        scenario: Scenario,
        step_intents: List[Dict[str, Any]],
        data_files: List[str],
    ) -> List[str]:
        keywords = set(self._terms(scenario.name))
        keywords.update(tag.lstrip("@").lower() for tag in scenario.tags + scenario.jira_tags)
        keywords.update(item["intent"] for item in step_intents)
        keywords.update(Path(path).stem.lower() for path in data_files)
        return sorted(keyword for keyword in keywords if keyword)

    def _data_files_from_steps(self, steps: List[Step]) -> List[str]:
        result = []
        for step in steps:
            for path in self.READ_PATTERN.findall(step.text):
                if path.lower().endswith((".json", ".csv", ".yaml", ".yml")):
                    result.append(path)
        return list(dict.fromkeys(result))

    def _status_codes(self, steps: List[Step]) -> List[str]:
        codes = []
        for step in steps:
            codes.extend(self.STATUS_CODE_PATTERN.findall(step.text))
        return sorted(set(codes))

    def _exact_duplicate_step_groups(
        self,
        min_group_size: int,
        include_low_signal: bool,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for feature, scenario in self._iter_scenarios():
            for index, step in enumerate(scenario.steps):
                if self._is_template_api_step(step.text):
                    continue
                signal = self._step_reuse_signal(step.text)
                if signal == "low" and not include_low_signal:
                    continue
                key = self._normalize_step_key(step.text)
                if not key:
                    continue
                grouped.setdefault(key, []).append(
                    self._step_location_payload(feature, scenario, step, index, signal)
                )

        groups = []
        for key, locations in grouped.items():
            if self._unique_scenario_count(locations) < min_group_size:
                continue
            first = locations[0]
            groups.append(
                {
                    "group_id": self._stable_group_id("dup_step", key),
                    "type": "exact_duplicate_step",
                    "step": first["step"],
                    "normalized_step": key,
                    "signal": first["signal"],
                    "location_count": len(locations),
                    "scenario_count": self._unique_scenario_count(locations),
                    "file_count": self._unique_file_count(locations),
                    "confidence": self._duplicate_confidence(first["signal"], len(locations), 1),
                    "reason": self._duplicate_reason("step", locations),
                    "locations": locations,
                    "ai_fix_plan": self._ai_fix_plan(
                        "exact_duplicate_step",
                        [first["step"]],
                        locations,
                        first["signal"],
                    ),
                }
            )
        return sorted(groups, key=self._duplicate_group_sort_key, reverse=True)

    def _duplicate_flow_groups(
        self,
        min_group_size: int,
        min_flow_length: int,
        include_low_signal: bool,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for feature, scenario in self._iter_scenarios():
            steps = scenario.steps
            max_window = min(len(steps), max(min_flow_length, 6))
            for window_size in range(min_flow_length, max_window + 1):
                for start in range(0, len(steps) - window_size + 1):
                    window = steps[start:start + window_size]
                    if all(self._is_template_api_step(step.text) for step in window):
                        continue
                    signals = [self._step_reuse_signal(step.text) for step in window]
                    if not include_low_signal and self._is_low_signal_flow(signals):
                        continue
                    signature = [
                        self._normalize_flow_step(step.text)
                        for step in window
                        if not self._is_template_api_step(step.text)
                    ]
                    signature = [item for item in signature if item]
                    if len(signature) < min_flow_length:
                        continue
                    key = "\n".join(signature)
                    grouped.setdefault(key, []).append(
                        self._flow_location_payload(
                            feature,
                            scenario,
                            window,
                            start,
                            signals,
                            signature,
                        )
                    )

        groups = []
        for key, locations in grouped.items():
            if self._unique_scenario_count(locations) < min_group_size:
                continue
            first = locations[0]
            signal = self._flow_signal(first["signals"])
            groups.append(
                {
                    "group_id": self._stable_group_id("dup_flow", key),
                    "type": "near_duplicate_flow",
                    "flow_length": first["flow_length"],
                    "normalized_flow": first["normalized_flow"],
                    "signal": signal,
                    "location_count": len(locations),
                    "scenario_count": self._unique_scenario_count(locations),
                    "file_count": self._unique_file_count(locations),
                    "confidence": self._duplicate_confidence(
                        signal,
                        len(locations),
                        first["flow_length"],
                    ),
                    "reason": self._duplicate_reason("flow", locations),
                    "locations": locations,
                    "ai_fix_plan": self._ai_fix_plan(
                        "near_duplicate_flow",
                        first["steps"],
                        locations,
                        signal,
                    ),
                }
            )
        return sorted(groups, key=self._duplicate_group_sort_key, reverse=True)

    def _step_location_payload(
        self,
        feature: Dict[str, Any],
        scenario: Scenario,
        step: Step,
        index: int,
        signal: str,
    ) -> Dict[str, Any]:
        return {
            "feature_file": feature["file_path"],
            "feature_name": feature["feature_name"],
            "scenario_name": scenario.name,
            "tags": scenario.tags,
            "jira_tags": scenario.jira_tags,
            "line_number": step.line_number,
            "step_index": index,
            "step": step.text,
            "intent": self._classify_step(step)["intent"],
            "signal": signal,
        }

    def _flow_location_payload(
        self,
        feature: Dict[str, Any],
        scenario: Scenario,
        window: List[Step],
        start: int,
        signals: List[str],
        signature: List[str],
    ) -> Dict[str, Any]:
        return {
            "feature_file": feature["file_path"],
            "feature_name": feature["feature_name"],
            "scenario_name": scenario.name,
            "tags": scenario.tags,
            "jira_tags": scenario.jira_tags,
            "start_line": window[0].line_number,
            "end_line": window[-1].line_number,
            "start_step_index": start,
            "flow_length": len(window),
            "steps": [step.text for step in window],
            "normalized_flow": signature,
            "signals": signals,
        }

    def _normalize_step_key(self, text: str) -> str:
        normalized = text.strip().lower().replace('"', "'")
        return re.sub(r"\s+", " ", normalized)

    def _normalize_flow_step(self, text: str) -> str:
        normalized = self._normalize_step_key(text)
        normalized = re.sub(r"\bstatus\s+\d{3}\b", "status <code>", normalized)
        normalized = re.sub(
            r"request\s+read\s*\(\s*'[^']+\.(json|csv|ya?ml)'\s*\)",
            "request read(<data-file>)",
            normalized,
        )
        normalized = re.sub(r"\bdef\s+[a-zA-Z_]\w*\s*=", "def <var> =", normalized)
        return normalized

    def _step_reuse_signal(self, text: str) -> str:
        if self._is_template_api_step(text):
            return "low"
        lower = text.lower()
        if "call read(" in lower or "callonce read(" in lower:
            return "high"
        if "java.type(" in lower or re.search(r"read\s*\([^)]*\.js", lower):
            return "high"
        if re.search(r"\brequest\s+read\s*\(", lower):
            return "high"
        if re.search(r"\bpath\s+['\"]", lower):
            return "medium"
        if re.search(r"\b(def|set)\b", lower):
            return "medium"
        if self._is_assertion_step(text) and not re.fullmatch(r"\s*status\s+\d{3}\s*", lower):
            return "medium"
        return "low"

    def _is_low_signal_flow(self, signals: List[str]) -> bool:
        return "high" not in signals and signals.count("medium") < 2

    def _flow_signal(self, signals: List[str]) -> str:
        if "high" in signals:
            return "high"
        if "medium" in signals:
            return "medium"
        return "low"

    def _duplicate_confidence(self, signal: str, location_count: int, flow_length: int) -> float:
        signal_weight = {"high": 0.3, "medium": 0.18, "low": 0.05}.get(signal, 0.1)
        count_weight = min(location_count, 5) * 0.05
        length_weight = min(flow_length, 6) * 0.04
        return round(min(0.95, 0.35 + signal_weight + count_weight + length_weight), 4)

    def _duplicate_reason(self, kind: str, locations: List[Dict[str, Any]]) -> str:
        scenario_count = self._unique_scenario_count(locations)
        file_count = self._unique_file_count(locations)
        noun = "step" if kind == "step" else "step flow"
        return f"Same {noun} appears in {scenario_count} scenario(s) across {file_count} file(s)."

    def _ai_fix_plan(
        self,
        group_type: str,
        steps: List[str],
        locations: List[Dict[str, Any]],
        signal: str,
    ) -> Dict[str, Any]:
        strategy = self._reuse_strategy(group_type, steps, locations, signal)
        rerun_tests = self._rerun_tags(locations)
        return {
            "safe_to_auto_apply": False,
            "strategy": strategy["strategy"],
            "reason": strategy["reason"],
            "suggested_component": strategy["suggested_component"],
            "affected_files": sorted({item["feature_file"] for item in locations}),
            "rerun_tests": rerun_tests,
            "checklist": [
                "Confirm the duplicated steps have the same business meaning.",
                "Extract the shared flow to common feature/background/helper only if inputs and assertions remain clear.",
                "Replace duplicated locations one by one and rerun the affected tags first.",
            ],
        }

    def _reuse_strategy(
        self,
        group_type: str,
        steps: List[str],
        locations: List[Dict[str, Any]],
        signal: str,
    ) -> Dict[str, str]:
        step_blob = "\n".join(steps).lower()
        if group_type == "exact_duplicate_step" and (
            "call read('classpath:common/" in step_blob
            or 'call read("classpath:common/' in step_blob
        ):
            return {
                "strategy": "keep_existing_common_call",
                "reason": "This duplicate is already expressed as a reusable common call.",
                "suggested_component": "",
            }

        first_name = locations[0].get("scenario_name", "shared-flow")
        component = f"common/reusable/{self._slugify(first_name)}.feature@SharedFlow"
        same_feature = self._unique_file_count(locations) == 1
        if group_type == "near_duplicate_flow" and same_feature:
            return {
                "strategy": "move_to_background_or_extract_common_feature",
                "reason": "The duplicate flow is repeated inside one feature file.",
                "suggested_component": component,
            }
        if group_type == "near_duplicate_flow":
            return {
                "strategy": "extract_common_feature",
                "reason": "The duplicate flow crosses scenarios/files and is a candidate for call read reuse.",
                "suggested_component": component,
            }
        if signal == "high":
            return {
                "strategy": "extract_helper_or_common_call",
                "reason": "The duplicated step references reusable data, feature, JavaScript, or Java logic.",
                "suggested_component": component,
            }
        return {
            "strategy": "review_before_refactor",
            "reason": "The duplicate may be intentional Karate grammar or readability scaffolding.",
            "suggested_component": "",
        }

    def _rerun_tags(self, locations: List[Dict[str, Any]]) -> List[str]:
        tags = []
        for item in locations:
            for tag in item.get("jira_tags") or item.get("tags") or []:
                if tag.startswith("@"):
                    tags.append(tag)
                    break
        return list(dict.fromkeys(tags))

    def _rank_reuse_candidates(
        self,
        exact_groups: List[Dict[str, Any]],
        flow_groups: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates = []
        for item in [*flow_groups, *exact_groups]:
            candidates.append(
                {
                    "group_id": item["group_id"],
                    "type": item["type"],
                    "confidence": item["confidence"],
                    "location_count": item["location_count"],
                    "scenario_count": item["scenario_count"],
                    "file_count": item["file_count"],
                    "reason": item["reason"],
                    "ai_fix_plan": item["ai_fix_plan"],
                }
            )
        return sorted(candidates, key=self._duplicate_group_sort_key, reverse=True)

    def _duplicate_group_sort_key(self, item: Dict[str, Any]) -> tuple:
        return (
            item.get("confidence", 0),
            item.get("scenario_count", 0),
            item.get("flow_length", 1),
            item.get("location_count", 0),
        )

    def _unique_scenario_count(self, locations: List[Dict[str, Any]]) -> int:
        return len(
            {
                (
                    item.get("feature_file"),
                    item.get("scenario_name"),
                    tuple(item.get("tags", [])),
                )
                for item in locations
            }
        )

    def _unique_file_count(self, locations: List[Dict[str, Any]]) -> int:
        return len({item.get("feature_file") for item in locations})

    def _stable_group_id(self, prefix: str, key: str) -> str:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{digest}"

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
        return slug or "shared-flow"

    def _is_template_api_step(self, text: str) -> bool:
        return bool(self.API_TEMPLATE_PATTERN.match(text.strip()))

    def _precondition_steps(self, step_intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        preconditions = []
        for item in step_intents:
            if item["intent"] in {"auth", "data-prepare", "call-reuse"}:
                preconditions.append(item)
        return preconditions

    def _action_steps(self, step_intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        actions = []
        for item in step_intents:
            if item["intent"] in {"request", "database", "ui"}:
                actions.append(item)
        return actions

    def _expectation_steps(self, step_intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [item for item in step_intents if item["intent"] == "assertion"]

    def _similar_neighbors(
        self,
        anchor: Dict[str, Any],
        entries: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        anchor_tokens = set(anchor.get("intent_keywords", []))
        if not anchor_tokens:
            return []

        scored: List[Dict[str, Any]] = []
        for candidate in entries:
            if (
                candidate["feature_file"] == anchor["feature_file"]
                and candidate["scenario_name"] == anchor["scenario_name"]
            ):
                continue
            candidate_tokens = set(candidate.get("intent_keywords", []))
            if not candidate_tokens:
                continue
            union = anchor_tokens | candidate_tokens
            if not union:
                continue
            score = len(anchor_tokens & candidate_tokens) / len(union)
            if score <= 0:
                continue
            scored.append(
                {
                    "feature_file": candidate["feature_file"],
                    "scenario_name": candidate["scenario_name"],
                    "tags": candidate["tags"],
                    "jira_tags": candidate["jira_tags"],
                    "score": round(score, 4),
                    "overlap_keywords": sorted(anchor_tokens & candidate_tokens),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def _config_references(self, steps: List[Step]) -> List[Dict[str, Any]]:
        config_keys = set(self.project.parser_config.variable_patterns.keys())
        config_keys.update(self.project.parser_config.base_url_mapping.keys())
        refs = []
        for step in steps:
            for key in config_keys:
                if key and re.search(rf"\b{re.escape(key)}\b", step.text):
                    refs.append({"name": key, "line_number": step.line_number, "step": step.text})
        return refs

    def _source_type(self, expression: str) -> str:
        lower = expression.lower()
        if "read(" in lower:
            if any(ext in lower for ext in [".json", ".csv", ".yaml", ".yml"]):
                return "data-file"
            if ".feature" in lower:
                return "feature-call"
            if ".js" in lower:
                return "javascript-helper"
        if "java.type" in lower:
            return "java-class"
        if "karate.get" in lower:
            return "karate-runtime"
        return "literal-or-expression"

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

    def _examples_payload(self, scenario: Scenario) -> Optional[Dict[str, Any]]:
        if not scenario.examples:
            return None
        return {
            "line_number": scenario.examples.line_number,
            "headers": scenario.examples.headers,
            "rows": scenario.examples.rows,
        }

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
