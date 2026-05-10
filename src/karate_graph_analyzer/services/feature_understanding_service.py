"""Feature understanding utilities for AI search, reuse, and debugging."""

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from karate_graph_analyzer.models import DependencyGraph, NodeType, Project, Scenario, Step
from karate_graph_analyzer.parser.extractors.call_read_extractor import CallReadExtractor
from karate_graph_analyzer.parser.feature_parser import FeatureFileParser


class FeatureUnderstandingService:
    """Build AI-ready indexes from Karate feature scenarios."""

    ASSERTION_PATTERN = re.compile(r"\b(status|match|assert)\b", re.IGNORECASE)
    DEF_PATTERN = re.compile(r"\bdef\s+([A-Za-z_][\w]*)\s*=\s*(.+)$")
    SET_PATTERN = re.compile(r"\bset\s+([A-Za-z_][\w.]*)\s*=\s*(.+)$")
    METHOD_PATTERN = re.compile(r"\bmethod\s+([A-Z]+|[A-Za-z_][\w]*)\b", re.IGNORECASE)
    STATUS_PATTERN = re.compile(r"\bstatus\s+(\d{3}|[A-Za-z_][\w]*)\b", re.IGNORECASE)
    READ_TARGET_PATTERN = re.compile(
        r"(?:call(?:once)?\s+)?read\s*\(\s*['\"]([^'\"]+)['\"]",
        re.IGNORECASE,
    )
    TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_/-]*")

    STOP_WORDS = {
        "and",
        "api",
        "call",
        "def",
        "given",
        "karate",
        "match",
        "method",
        "path",
        "read",
        "request",
        "response",
        "status",
        "then",
        "url",
        "when",
    }

    LOW_SIGNAL_STEP_PATTERNS = [
        re.compile(r"^(?:when\s+)?method\s+\w+$", re.IGNORECASE),
        re.compile(r"^(?:then\s+)?status\s+\d{3}$", re.IGNORECASE),
        re.compile(r"^url\b", re.IGNORECASE),
        re.compile(r"^path\b", re.IGNORECASE),
        re.compile(r"^request\b", re.IGNORECASE),
        re.compile(r"^print\b", re.IGNORECASE),
    ]

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
        scenarios = [self._intent_payload(feature, scenario) for feature, scenario in self._iter_scenarios()]
        if query:
            terms = self._terms(query)
            scenarios = [item for item in scenarios if self._entry_matches(item, terms)]

        return {
            "scenarios": scenarios[:limit],
            "count": min(len(scenarios), limit),
            "total_available": len(scenarios),
        }

    def variable_data_flow_trace(
        self,
        feature_path: Optional[str] = None,
        scenario_tag: Optional[str] = None,
        scenario_name: Optional[str] = None,
        node_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        traces = []
        for feature, scenario in self._matching_scenarios(feature_path, scenario_tag, scenario_name, node_id):
            traces.append(
                {
                    "feature_file": feature["file_path"],
                    "scenario_name": scenario.name,
                    "line_number": scenario.line_number,
                    "tags": scenario.tags,
                    "jira_tags": scenario.jira_tags,
                    "variables": self._variable_trace_for_scenario(feature, scenario),
                }
            )

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
                assertions.append(
                    {
                        "feature_file": feature["file_path"],
                        "scenario_name": scenario.name,
                        "line_number": step.line_number,
                        "step": step.text,
                        "assertion_type": self._assertion_type(step.text),
                        "tags": scenario.tags,
                        "jira_tags": scenario.jira_tags,
                    }
                )

        if query:
            terms = self._terms(query)
            assertions = [item for item in assertions if self._entry_matches(item, terms)]

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
        for feature, scenario in self._matching_scenarios(feature_path, scenario_tag, scenario_name, node_id):
            contexts.append(
                {
                    "feature_file": feature["file_path"],
                    "scenario_name": scenario.name,
                    "line_number": scenario.line_number,
                    "tags": scenario.tags,
                    "jira_tags": scenario.jira_tags,
                    "calls": self._call_tree(feature, scenario, max_depth=max_depth),
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
        for feature, scenario in self._matching_scenarios(feature_path, scenario_tag, scenario_name, node_id):
            packs.append(
                {
                    "identity": self._scenario_identity(feature, scenario),
                    "intent": self._intent_payload(feature, scenario),
                    "variable_flow": self._variable_trace_for_scenario(feature, scenario),
                    "assertions": self._assertions_for_scenario(feature, scenario),
                    "call_read_context": self._call_tree(feature, scenario, max_depth=max_call_depth),
                    "behavior": self._behavior_for_scenario(feature, scenario),
                    "graph_context": self._graph_context(feature, scenario),
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
        for feature, scenario in self._matching_scenarios(feature_path, scenario_tag, scenario_name, node_id):
            maps.append(self._behavior_for_scenario(feature, scenario))

        return {
            "scenarios": maps[:limit],
            "count": min(len(maps), limit),
            "total_available": len(maps),
        }

    def scenario_similarity_map(
        self,
        query: Optional[str] = None,
        limit: int = 50,
        top_k: int = 3,
    ) -> Dict[str, Any]:
        payloads = [self._intent_payload(feature, scenario) for feature, scenario in self._iter_scenarios()]
        candidates = payloads
        if query:
            terms = self._terms(query)
            candidates = [item for item in payloads if self._entry_matches(item, terms)]

        anchors = []
        for item in candidates[:limit]:
            item_keywords = set(item.get("keywords", []))
            similar = []
            for other in payloads:
                if other["node_key"] == item["node_key"]:
                    continue
                other_keywords = set(other.get("keywords", []))
                score = self._similarity_score(item_keywords, other_keywords)
                if score <= 0:
                    continue
                similar.append(
                    {
                        "score": score,
                        "scenario_name": other["scenario_name"],
                        "feature_file": other["feature_file"],
                        "line_number": other["line_number"],
                        "jira_tags": other["jira_tags"],
                        "overlap_keywords": sorted(item_keywords & other_keywords),
                    }
                )
            similar.sort(key=lambda value: value["score"], reverse=True)
            anchors.append({**item, "similar_scenarios": similar[:top_k]})

        return {
            "anchors": anchors,
            "count": len(anchors),
            "total_available": len(candidates),
        }

    def feature_reuse_advisor(
        self,
        min_group_size: int = 2,
        min_flow_length: int = 3,
        limit: int = 50,
        include_low_signal: bool = False,
    ) -> Dict[str, Any]:
        step_groups = self._duplicate_step_groups(min_group_size, include_low_signal)
        flow_groups = self._duplicate_flow_groups(min_group_size, min_flow_length, include_low_signal)
        suggestions = self._reuse_suggestions(step_groups, flow_groups)

        return {
            "duplicate_steps": step_groups[:limit],
            "duplicate_flows": flow_groups[:limit],
            "refactor_suggestions": suggestions[:limit],
            "count": min(len(step_groups) + len(flow_groups), limit),
            "total_available": len(step_groups) + len(flow_groups),
            "ignored_low_signal_steps": not include_low_signal,
        }

    def _intent_payload(self, feature: Dict[str, Any], scenario: Scenario) -> Dict[str, Any]:
        all_steps = feature["background_steps"] + scenario.steps
        assertions = self._assertions_for_scenario(feature, scenario)
        call_reads = self._call_reads_for_steps(all_steps)
        variables = self._defined_variables(all_steps)
        api_signals = self._api_signals(all_steps)
        data_files = self._data_files(all_steps)
        keywords = self._intent_keywords(scenario.name, all_steps)

        return {
            **self._scenario_identity(feature, scenario),
            "node_key": self._scenario_key(feature, scenario),
            "intent": self._summarize_intent(scenario, keywords, assertions, call_reads),
            "keywords": keywords,
            "step_count": len(scenario.steps),
            "background_step_count": len(feature["background_steps"]),
            "variables": [item["name"] for item in variables],
            "api_signals": api_signals,
            "data_files": data_files,
            "assertions": assertions,
            "call_reads": call_reads,
        }

    def _behavior_for_scenario(self, feature: Dict[str, Any], scenario: Scenario) -> Dict[str, Any]:
        all_steps = feature["background_steps"] + scenario.steps
        preconditions: List[Dict[str, Any]] = []
        actions: List[Dict[str, Any]] = []
        expectations: List[Dict[str, Any]] = []

        for step in all_steps:
            payload = {"line_number": step.line_number, "step": step.text}
            role = self._step_role(step.text)
            if role == "expectation":
                expectations.append(payload)
            elif role == "action":
                actions.append(payload)
            else:
                preconditions.append(payload)

        return {
            **self._scenario_identity(feature, scenario),
            "preconditions": preconditions,
            "actions": actions,
            "expectations": expectations,
            "data_inputs": self._data_files(all_steps),
            "status_expectations": self._status_expectations(all_steps),
        }

    def _variable_trace_for_scenario(
        self,
        feature: Dict[str, Any],
        scenario: Scenario,
    ) -> List[Dict[str, Any]]:
        all_steps = feature["background_steps"] + scenario.steps
        definitions = self._defined_variables(all_steps)
        return [
            {
                **definition,
                "used_at": self._variable_usages(definition["name"], all_steps, definition["line_number"]),
            }
            for definition in definitions
        ]

    def _assertions_for_scenario(
        self,
        feature: Dict[str, Any],
        scenario: Scenario,
    ) -> List[Dict[str, Any]]:
        return [
            {
                "feature_file": feature["file_path"],
                "scenario_name": scenario.name,
                "line_number": step.line_number,
                "step": step.text,
                "assertion_type": self._assertion_type(step.text),
            }
            for step in scenario.steps
            if self._is_assertion_step(step.text)
        ]

    def _call_tree(
        self,
        feature: Dict[str, Any],
        scenario: Scenario,
        max_depth: int,
        depth: int = 0,
        visited: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        visited = visited or set()
        key = self._scenario_key(feature, scenario)
        if key in visited:
            return []
        visited.add(key)

        calls = []
        for call in self._call_reads_for_steps(feature["background_steps"] + scenario.steps):
            resolved_path, target_tag = self._resolve_read_path(call["target"])
            target_scenarios = self._target_scenarios(resolved_path, target_tag)
            call_payload = {
                **call,
                "resolved_path": resolved_path,
                "target_scenario_tag": target_tag,
                "target_scenarios": [
                    {
                        "scenario_name": target.name,
                        "line_number": target.line_number,
                        "tags": target.tags,
                        "jira_tags": target.jira_tags,
                    }
                    for _, target in target_scenarios
                ],
                "children": [],
            }
            if depth < max_depth:
                for target_feature, target in target_scenarios:
                    call_payload["children"].extend(
                        self._call_tree(
                            target_feature,
                            target,
                            max_depth=max_depth,
                            depth=depth + 1,
                            visited=set(visited),
                        )
                    )
            calls.append(call_payload)

        return calls

    def _duplicate_step_groups(
        self,
        min_group_size: int,
        include_low_signal: bool,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        examples: Dict[str, str] = {}
        for feature, scenario in self._iter_scenarios():
            for step in scenario.steps:
                normalized = self._normalize_step(step.text)
                if not normalized:
                    continue
                if not include_low_signal and self._is_low_signal_step(normalized):
                    continue
                grouped[normalized].append(self._location(feature, scenario, step.line_number))
                examples.setdefault(normalized, step.text)

        rows = []
        for normalized, locations in grouped.items():
            if len(locations) < min_group_size:
                continue
            rows.append(
                {
                    "kind": "duplicate_step",
                    "normalized_step": normalized,
                    "example_step": examples[normalized],
                    "occurrence_count": len(locations),
                    "locations": locations,
                    "suggestion": "Extract this repeated step into a common feature/page/service scenario when the surrounding flow is stable.",
                }
            )
        rows.sort(key=lambda item: item["occurrence_count"], reverse=True)
        return rows

    def _duplicate_flow_groups(
        self,
        min_group_size: int,
        min_flow_length: int,
        include_low_signal: bool,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[str, ...], List[Dict[str, Any]]] = defaultdict(list)
        examples: Dict[Tuple[str, ...], List[str]] = {}
        for feature, scenario in self._iter_scenarios():
            steps = [
                (self._normalize_step(step.text), step)
                for step in scenario.steps
                if include_low_signal or not self._is_low_signal_step(self._normalize_step(step.text))
            ]
            steps = [(text, step) for text, step in steps if text]
            if len(steps) < min_flow_length:
                continue

            for index in range(0, len(steps) - min_flow_length + 1):
                window = tuple(text for text, _ in steps[index : index + min_flow_length])
                first_step = steps[index][1]
                grouped[window].append(self._location(feature, scenario, first_step.line_number))
                examples.setdefault(window, [step.text for _, step in steps[index : index + min_flow_length]])

        rows = []
        for window, locations in grouped.items():
            if len(locations) < min_group_size:
                continue
            rows.append(
                {
                    "kind": "duplicate_flow",
                    "normalized_flow": list(window),
                    "example_steps": examples[window],
                    "occurrence_count": len(locations),
                    "locations": locations,
                    "suggestion": "Consider extracting this repeated flow into a reusable scenario with a clear tag and parameters.",
                }
            )
        rows.sort(key=lambda item: (item["occurrence_count"], len(item["normalized_flow"])), reverse=True)
        return rows

    def _reuse_suggestions(
        self,
        step_groups: List[Dict[str, Any]],
        flow_groups: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        suggestions = []
        for item in flow_groups[:10]:
            suggestions.append(
                {
                    "priority": item["occurrence_count"] * len(item["normalized_flow"]),
                    "type": "extract_reusable_flow",
                    "locations": item["locations"],
                    "reason": f"{item['occurrence_count']} scenarios repeat a {len(item['normalized_flow'])}-step flow.",
                    "recommended_shape": "common/services/<domain>/<Action>.feature@ReusableAction",
                }
            )
        for item in step_groups[:10]:
            suggestions.append(
                {
                    "priority": item["occurrence_count"],
                    "type": "extract_or_alias_step",
                    "locations": item["locations"],
                    "reason": f"{item['occurrence_count']} scenarios repeat the same step.",
                    "recommended_shape": "reuse an existing helper, or keep inline if it is only Karate grammar.",
                }
            )
        suggestions.sort(key=lambda item: item["priority"], reverse=True)
        return suggestions

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

    def _iter_scenarios(self) -> Iterable[Tuple[Dict[str, Any], Scenario]]:
        for feature in self._feature_asts():
            for scenario in feature["scenarios"]:
                yield feature, scenario

    def _matching_scenarios(
        self,
        feature_path: Optional[str],
        scenario_tag: Optional[str],
        scenario_name: Optional[str],
        node_id: Optional[str],
    ) -> List[Tuple[Dict[str, Any], Scenario]]:
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

    def _scenario_identity(self, feature: Dict[str, Any], scenario: Scenario) -> Dict[str, Any]:
        return {
            "feature_file": feature["file_path"],
            "feature_name": feature.get("feature_name"),
            "scenario_name": scenario.name,
            "line_number": scenario.line_number,
            "tags": scenario.tags,
            "jira_tags": scenario.jira_tags,
            "test_case_id": scenario.jira_tags[0].lstrip("@") if scenario.jira_tags else None,
        }

    def _scenario_key(self, feature: Dict[str, Any], scenario: Scenario) -> str:
        return f"{feature['file_path']}:{scenario.line_number}:{scenario.name}"

    def _defined_variables(self, steps: List[Step]) -> List[Dict[str, Any]]:
        definitions = []
        for step in steps:
            match = self.DEF_PATTERN.search(step.text) or self.SET_PATTERN.search(step.text)
            if not match:
                continue
            definitions.append(
                {
                    "name": match.group(1),
                    "expression": match.group(2).strip(),
                    "line_number": step.line_number,
                    "source_step": step.text,
                }
            )
        return definitions

    def _variable_usages(
        self,
        variable_name: str,
        steps: List[Step],
        definition_line: int,
    ) -> List[Dict[str, Any]]:
        pattern = re.compile(rf"\b{re.escape(variable_name)}\b")
        return [
            {"line_number": step.line_number, "step": step.text}
            for step in steps
            if step.line_number != definition_line and pattern.search(step.text)
        ]

    def _call_reads_for_steps(self, steps: List[Step]) -> List[Dict[str, Any]]:
        calls = []
        for step in steps:
            for match in self.READ_TARGET_PATTERN.finditer(step.text):
                calls.append(
                    {
                        "line_number": step.line_number,
                        "step": step.text,
                        "target": match.group(1),
                    }
                )
        return calls

    def _api_signals(self, steps: List[Step]) -> List[Dict[str, Any]]:
        signals = []
        for step in steps:
            lowered = step.text.lower()
            method = self.METHOD_PATTERN.search(step.text)
            status = self.STATUS_PATTERN.search(step.text)
            if method or status or lowered.startswith(("url ", "path ")):
                signals.append(
                    {
                        "line_number": step.line_number,
                        "step": step.text,
                        "method": method.group(1).upper() if method else None,
                        "status": status.group(1) if status else None,
                    }
                )
        return signals

    def _data_files(self, steps: List[Step]) -> List[Dict[str, Any]]:
        data = []
        for step in steps:
            for target in self.READ_TARGET_PATTERN.findall(step.text):
                if re.search(r"\.(json|csv|yaml|yml|xml|txt)$", target, re.IGNORECASE):
                    data.append({"line_number": step.line_number, "target": target, "step": step.text})
        return data

    def _status_expectations(self, steps: List[Step]) -> List[Dict[str, Any]]:
        rows = []
        for step in steps:
            match = self.STATUS_PATTERN.search(step.text)
            if match:
                rows.append({"line_number": step.line_number, "status": match.group(1), "step": step.text})
        return rows

    def _is_assertion_step(self, step_text: str) -> bool:
        return bool(self.ASSERTION_PATTERN.search(step_text))

    def _assertion_type(self, step_text: str) -> str:
        lowered = step_text.lower()
        if "status" in lowered:
            return "status"
        if "match" in lowered:
            return "match"
        if "assert" in lowered:
            return "assert"
        return "unknown"

    def _step_role(self, step_text: str) -> str:
        lowered = step_text.lower()
        if self._is_assertion_step(step_text):
            return "expectation"
        if " method " in f" {lowered} " or lowered.startswith(("call ", "click ", "submit ", "input ")):
            return "action"
        return "precondition"

    def _intent_keywords(self, scenario_name: str, steps: List[Step]) -> List[str]:
        text = " ".join([scenario_name] + [step.text for step in steps])
        counts = Counter(
            token.lower()
            for token in self.TOKEN_PATTERN.findall(text)
            if len(token) >= 3 and token.lower() not in self.STOP_WORDS
        )
        return [token for token, _ in counts.most_common(20)]

    def _summarize_intent(
        self,
        scenario: Scenario,
        keywords: List[str],
        assertions: List[Dict[str, Any]],
        call_reads: List[Dict[str, Any]],
    ) -> str:
        signals = []
        if keywords:
            signals.append(f"keywords={', '.join(keywords[:5])}")
        if assertions:
            signals.append(f"assertions={len(assertions)}")
        if call_reads:
            signals.append(f"call_reads={len(call_reads)}")
        suffix = f" ({'; '.join(signals)})" if signals else ""
        return f"{scenario.name}{suffix}"

    def _resolve_read_path(self, target: str) -> Tuple[Optional[str], Optional[str]]:
        clean_target, target_tag = self._split_feature_target(target)
        if not clean_target or "${" in clean_target or "#(" in clean_target:
            return None, target_tag

        raw = clean_target.replace("classpath:", "").replace("\\", "/").lstrip("/")
        raw_path = Path(raw)
        candidates = []
        if raw_path.is_absolute():
            candidates.append(raw_path)
        candidates.extend(
            [
                self.root / raw,
                self.root / "src/test/java" / raw,
                self.root / "src/test/resources" / raw,
            ]
        )
        for candidate in candidates:
            if candidate.exists():
                return str(candidate.resolve()), target_tag
        return None, target_tag

    def _split_feature_target(self, target: str) -> Tuple[str, Optional[str]]:
        if ".feature@" not in target:
            return target, None
        path_part, tag_part = target.split(".feature@", 1)
        return f"{path_part}.feature", f"@{tag_part}" if not tag_part.startswith("@") else tag_part

    def _target_scenarios(
        self,
        resolved_path: Optional[str],
        scenario_tag: Optional[str],
    ) -> List[Tuple[Dict[str, Any], Scenario]]:
        if not resolved_path:
            return []
        for feature in self._feature_asts():
            if not self._path_matches(feature["file_path"], resolved_path):
                continue
            scenarios = feature["scenarios"]
            if scenario_tag:
                scenarios = [
                    scenario
                    for scenario in scenarios
                    if self._tag_matches(scenario.tags + scenario.jira_tags, scenario_tag)
                ]
            return [(feature, scenario) for scenario in scenarios]
        return []

    def _graph_context(self, feature: Dict[str, Any], scenario: Scenario) -> Dict[str, Any]:
        node_id = self._find_scenario_node_id(feature, scenario)
        if not node_id or not self.graph:
            return {}

        outgoing = []
        incoming = []
        for edge in self.graph.edges.values():
            if edge.from_node == node_id:
                target = self.graph.nodes.get(edge.to_node)
                outgoing.append(
                    {
                        "node_id": edge.to_node,
                        "name": target.name if target else edge.to_node,
                        "type": target.type.value if target else None,
                        "edge_type": edge.type.value,
                    }
                )
            if edge.to_node == node_id:
                source = self.graph.nodes.get(edge.from_node)
                incoming.append(
                    {
                        "node_id": edge.from_node,
                        "name": source.name if source else edge.from_node,
                        "type": source.type.value if source else None,
                        "edge_type": edge.type.value,
                    }
                )
        return {"node_id": node_id, "outgoing": outgoing[:20], "incoming": incoming[:20]}

    def _find_scenario_node_id(self, feature: Dict[str, Any], scenario: Scenario) -> Optional[str]:
        if not self.graph:
            return None
        for node_id, node in self.graph.nodes.items():
            if node.type not in {NodeType.TEST_CASE, NodeType.SCENARIO, NodeType.ACTION}:
                continue
            if node.metadata.file_path and not self._path_matches(feature["file_path"], node.metadata.file_path):
                continue
            if node.metadata.line_number == scenario.line_number:
                return node_id
            if scenario.name in node.name or node.name in scenario.name:
                return node_id
        return None

    def _normalize_step(self, step_text: str) -> str:
        normalized = re.sub(r"\s+", " ", step_text.strip())
        normalized = re.sub(r"['\"][^'\"]+['\"]", "<string>", normalized)
        normalized = re.sub(r"\b\d+\b", "<number>", normalized)
        return normalized.lower()

    def _is_low_signal_step(self, normalized_step: str) -> bool:
        return any(pattern.search(normalized_step) for pattern in self.LOW_SIGNAL_STEP_PATTERNS)

    def _location(
        self,
        feature: Dict[str, Any],
        scenario: Scenario,
        line_number: int,
    ) -> Dict[str, Any]:
        return {
            "feature_file": feature["file_path"],
            "scenario_name": scenario.name,
            "line_number": line_number,
            "tags": scenario.tags,
            "jira_tags": scenario.jira_tags,
        }

    def _similarity_score(self, left: Set[str], right: Set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = left & right
        union = left | right
        return round(len(intersection) / len(union), 3)

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
