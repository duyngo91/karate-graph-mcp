"""Search source functions that can be reused before adding new helpers."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from karate_graph_analyzer.graph.graph_query import GraphQuery
from karate_graph_analyzer.models import DependencyGraph, Node, NodeType
from karate_graph_analyzer.parser.extractors.javascript_structure_extractor import (
    JavaScriptStructureExtractor,
)
from karate_graph_analyzer.utils.source_snippet import get_source_snippet


class ReusableFunctionSearchService:
    """Find Java/JavaScript helper candidates by name and source content."""

    EXCLUDED_DIRS = {
        ".git",
        ".karate_cache",
        "__pycache__",
        "build",
        "node_modules",
        "target",
    }

    JAVA_METHOD_PATTERNS = [
        re.compile(
            r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*"
            r"(?:(?:public|private|protected|static|final|synchronized|abstract|native|default)\s+)+"
            r"(?P<return_type>[\w<>\[\],.? ]+)\s+"
            r"(?P<name>[A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*(?:throws\s+[^{;]+)?[;{]",
            re.MULTILINE,
        ),
        re.compile(
            r"^\s*(?!if\b|for\b|while\b|switch\b|catch\b|return\b|new\b)"
            r"(?P<return_type>[A-Za-z_$][\w$<>\[\],.? ]+)\s+"
            r"(?P<name>[A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*(?:throws\s+[^{;]+)?[;{]",
            re.MULTILINE,
        ),
    ]
    ALIAS_GROUPS = {
        "random": ["rand", "rnd", "randomize", "uuid", "idgen", "faker"],
        "string": ["str", "text", "name"],
        "number": ["num", "int", "digit", "long"],
        "date": ["time", "timestamp", "now"],
        "auth": ["token", "login", "signin", "oauth", "jwt"],
        "api": ["endpoint", "request", "http", "client"],
        "db": ["database", "sql", "query", "jdbc", "repository"],
        "page": ["ui", "screen", "view", "action"],
    }

    TAG_KEYWORDS = {
        "random": ["random", "rand", "uuid"],
        "auth": ["auth", "login", "token", "jwt", "oauth", "signin"],
        "date": ["date", "time", "timestamp", "now"],
        "api-client": ["api", "http", "request", "endpoint", "client"],
        "database": ["db", "database", "sql", "query", "jdbc", "repository"],
        "page": ["page", "screen", "view", "ui", "action", "click"],
        "payload-builder": ["payload", "body", "json", "request"],
        "string": ["string", "text", "name"],
        "number": ["number", "num", "int", "digit"],
    }

    def search(
        self,
        project_root: Optional[str],
        graph: DependencyGraph,
        query_api: GraphQuery,
        query: str,
        language: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        terms = self._query_terms(query)
        if not terms:
            return {
                "success": False,
                "error": {
                    "code": "REUSABLE_SEARCH_EMPTY_QUERY",
                    "message": "Query must not be empty",
                },
            }

        languages = self._normalize_languages(language)
        graph_index = self._build_graph_index(graph, query_api)
        candidates: List[Dict[str, Any]] = []

        root = Path(project_root).resolve() if project_root else None
        if root and root.exists():
            if "javascript" in languages:
                candidates.extend(self._scan_javascript(root, terms, graph_index))
            if "java" in languages:
                candidates.extend(self._scan_java(root, terms, graph_index))

        candidates.extend(self._graph_only_candidates(graph, query_api, terms, languages))
        results = self._dedupe_and_rank(candidates, limit)
        return {
            "success": True,
            "query": query,
            "language": language or "all",
            "limit": limit,
            "results": results,
            "count": len(results),
            "total_available": len(self._dedupe_and_rank(candidates, len(candidates) or 1)),
        }

    def _query_terms(self, query: str) -> List[str]:
        return [term for term in re.split(r"[^A-Za-z0-9_$]+", query.lower()) if term]

    def _normalize_languages(self, language: Optional[str]) -> Set[str]:
        if not language or language.lower() in {"all", "*"}:
            return {"java", "javascript"}
        normalized = language.lower()
        if normalized in {"js", "javascript"}:
            return {"javascript"}
        if normalized == "java":
            return {"java"}
        return {"java", "javascript"}

    def _scan_javascript(
        self,
        root: Path,
        terms: List[str],
        graph_index: Dict[Tuple[str, str, str], Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        extractor = JavaScriptStructureExtractor()
        candidates = []
        for file_path in self._iter_source_files(root, ".js"):
            try:
                structure = extractor.parse_file(str(file_path))
            except OSError:
                continue

            for function in structure.functions:
                graph_hit = self._find_graph_hit(
                    graph_index,
                    "javascript",
                    str(file_path),
                    function.name,
                )
                candidate = self._build_candidate(
                    language="javascript",
                    name=function.name,
                    kind=function.kind,
                    file_path=str(file_path),
                    line_number=function.line_number,
                    terms=terms,
                    graph_hit=graph_hit,
                    search_text=self._source_block(file_path, function.line_number),
                )
                if candidate["score"] > 0:
                    candidates.append(candidate)
        return candidates

    def _scan_java(
        self,
        root: Path,
        terms: List[str],
        graph_index: Dict[Tuple[str, str, str], Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates = []
        for file_path in self._iter_source_files(root, ".java"):
            content = self._read_text(file_path)
            if content is None:
                continue
            seen_at_line = set()
            for pattern in self.JAVA_METHOD_PATTERNS:
                for match in pattern.finditer(content):
                    name = match.group("name")
                    line_number = content[: match.start()].count("\n") + 1
                    key = (name, line_number)
                    if key in seen_at_line:
                        continue
                    seen_at_line.add(key)
                    graph_hit = self._find_graph_hit(graph_index, "java", str(file_path), name)
                    candidate = self._build_candidate(
                        language="java",
                        name=name,
                        kind="java_method",
                        file_path=str(file_path),
                        line_number=line_number,
                        terms=terms,
                        graph_hit=graph_hit,
                        return_type=(match.groupdict().get("return_type") or "").strip(),
                        search_text=self._source_block(file_path, line_number),
                    )
                    if candidate["score"] > 0:
                        candidates.append(candidate)
        return candidates

    def _iter_source_files(self, root: Path, suffix: str) -> List[Path]:
        files = []
        for file_path in root.rglob(f"*{suffix}"):
            parts = {part.lower() for part in file_path.parts}
            if parts.intersection(self.EXCLUDED_DIRS):
                continue
            files.append(file_path)
        return files

    def _read_text(self, file_path: Path) -> Optional[str]:
        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

    def _source_block(self, file_path: Path, line_number: int, max_lines: int = 80) -> str:
        content = self._read_text(file_path)
        if content is None:
            return ""

        lines = content.splitlines()
        start_idx = max(line_number - 1, 0)
        selected = []
        depth = 0
        found_open = False
        for line in lines[start_idx : start_idx + max_lines]:
            selected.append(line)
            for char in line:
                if char == "{":
                    depth += 1
                    found_open = True
                elif char == "}":
                    depth -= 1
            if found_open and depth <= 0:
                break
            if not found_open and len(selected) >= 1:
                break
        return "\n".join(selected)

    def _build_graph_index(
        self,
        graph: DependencyGraph,
        query_api: GraphQuery,
    ) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
        index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for node in graph.nodes.values():
            if node.type not in {NodeType.JAVA_METHOD, NodeType.JS_FUNCTION}:
                continue
            language = "javascript" if node.type == NodeType.JS_FUNCTION else "java"
            data = node.metadata.additional_data
            file_path = (
                data.get("script_path")
                or data.get("file_path")
                or node.metadata.file_path
                or ""
            )
            name = data.get("function_name") or data.get("method_name") or node.name
            payload = self._graph_payload(node, query_api)
            index[(language, self._norm_path(str(file_path)), str(name).lower())] = payload
            index[(language, "", str(name).lower())] = payload
        return index

    def _find_graph_hit(
        self,
        graph_index: Dict[Tuple[str, str, str], Dict[str, Any]],
        language: str,
        file_path: str,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        norm_name = name.lower()
        return (
            graph_index.get((language, self._norm_path(file_path), norm_name))
            or graph_index.get((language, "", norm_name))
        )

    def _graph_payload(self, node: Node, query_api: GraphQuery) -> Dict[str, Any]:
        stats = query_api.get_usage_stats(node)
        usage_examples = self._build_usage_examples(node, query_api, limit=3)
        stability_score = self._calculate_stability_score(node, stats, query_api)
        return {
            "graph_node_id": node.id,
            "graph_node_type": node.type.value,
            "usage_count": stats.get("usage_count", 0),
            "used_by_test_cases": stats.get("used_by_test_cases", []),
            "usage_examples": usage_examples,
            "stability_score": stability_score,
        }

    def _build_candidate(
        self,
        language: str,
        name: str,
        kind: str,
        file_path: str,
        line_number: int,
        terms: List[str],
        graph_hit: Optional[Dict[str, Any]],
        return_type: str = "",
        search_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        snippet = get_source_snippet(file_path, line_number, context_lines=4)
        inferred_tags = self._infer_tags(name, search_text or snippet)
        aliases = self._build_aliases(name, inferred_tags)
        score, reasons = self._score_candidate(
            name=name,
            snippet=search_text or snippet,
            terms=terms,
            graph_hit=graph_hit,
            aliases=aliases,
            tags=inferred_tags,
        )
        usage_count = graph_hit.get("usage_count", 0) if graph_hit else 0
        return {
            "language": language,
            "name": name,
            "kind": kind,
            "return_type": return_type,
            "file_path": file_path,
            "line_number": line_number,
            "score": score,
            "match_reasons": reasons,
            "usage_count": usage_count,
            "graph_node_id": graph_hit.get("graph_node_id") if graph_hit else None,
            "graph_node_type": graph_hit.get("graph_node_type") if graph_hit else None,
            "used_by_test_cases": graph_hit.get("used_by_test_cases", []) if graph_hit else [],
            "usage_examples": graph_hit.get("usage_examples", []) if graph_hit else [],
            "tags": inferred_tags,
            "aliases": aliases,
            "stability_score": graph_hit.get("stability_score", 0.0) if graph_hit else 0.0,
            "source_snippet": snippet,
        }

    def _score_candidate(
        self,
        name: str,
        snippet: str,
        terms: List[str],
        graph_hit: Optional[Dict[str, Any]],
        aliases: List[str],
        tags: List[str],
    ) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        name_text = name.lower()
        source_text = snippet.lower()
        alias_text = " ".join(aliases).lower()
        tag_text = " ".join(tags).lower()
        combined_text = f"{name_text} {source_text} {alias_text} {tag_text}"

        if not all(term in combined_text for term in terms):
            return 0, []

        if all(term in name_text for term in terms):
            score += 80
            reasons.append("function_name")
        else:
            name_hits = [term for term in terms if term in name_text]
            if name_hits:
                score += 25 + (10 * len(name_hits))
                reasons.append("partial_name")

        source_hits = [term for term in terms if term in source_text]
        if len(source_hits) == len(terms):
            score += 35
            reasons.append("source_snippet")
        elif source_hits:
            score += 8 * len(source_hits)
            reasons.append("partial_source")

        alias_hits = [term for term in terms if term in alias_text]
        if alias_hits:
            score += 10 * len(alias_hits)
            reasons.append("alias_match")

        tag_hits = [term for term in terms if term in tag_text]
        if tag_hits:
            score += 12 * len(tag_hits)
            reasons.append("tag_match")

        usage_count = graph_hit.get("usage_count", 0) if graph_hit else 0
        if score > 0 and usage_count:
            score += min(usage_count, 20)
            reasons.append("already_used")

        stability_score = graph_hit.get("stability_score", 0.0) if graph_hit else 0.0
        if score > 0 and stability_score > 0:
            score += int(stability_score * 20)
            reasons.append("stability")

        return score, reasons

    def _graph_only_candidates(
        self,
        graph: DependencyGraph,
        query_api: GraphQuery,
        terms: List[str],
        languages: Set[str],
    ) -> List[Dict[str, Any]]:
        candidates = []
        for node in graph.nodes.values():
            language = None
            kind = node.type.value.lower()
            if node.type == NodeType.JAVA_METHOD:
                language = "java"
            elif node.type == NodeType.JS_FUNCTION:
                language = "javascript"
            if language not in languages:
                continue

            data = node.metadata.additional_data
            name = str(data.get("function_name") or data.get("method_name") or node.name)
            file_path = data.get("script_path") or data.get("file_path") or node.metadata.file_path
            if file_path and Path(str(file_path)).exists():
                continue
            line_number = node.metadata.line_number or 1
            graph_hit = self._graph_payload(node, query_api)
            candidate = self._build_candidate(
                language=language,
                name=name,
                kind=kind,
                file_path=str(file_path or ""),
                line_number=line_number,
                terms=terms,
                graph_hit=graph_hit,
            )
            if candidate["score"] > 0:
                candidates.append(candidate)
        return candidates

    def _dedupe_and_rank(self, candidates: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        best_by_key: Dict[Tuple[str, str, int, str], Dict[str, Any]] = {}
        for candidate in candidates:
            key = (
                candidate["language"],
                self._norm_path(candidate.get("file_path") or ""),
                candidate.get("line_number") or 0,
                candidate["name"].lower(),
            )
            current = best_by_key.get(key)
            if current is None or candidate["score"] > current["score"]:
                best_by_key[key] = candidate

        ranked = sorted(
            best_by_key.values(),
            key=lambda item: (
                item.get("score", 0),
                item.get("usage_count", 0),
                item.get("language", ""),
                item.get("name", ""),
            ),
            reverse=True,
        )
        return ranked[: max(limit, 0)]

    def _norm_path(self, path: str) -> str:
        return path.replace("\\", "/").lower()

    def _infer_tags(self, name: str, source_text: str) -> List[str]:
        text = f"{name} {source_text}".lower()
        tokens = {token for token in re.split(r"[^a-z0-9_]+", text) if token}
        tags: List[str] = []
        for tag, keywords in self.TAG_KEYWORDS.items():
            matched = False
            for keyword in keywords:
                if len(keyword) <= 3:
                    if keyword in tokens:
                        matched = True
                        break
                elif keyword in text:
                    matched = True
                    break
            if matched:
                tags.append(tag)
        return tags

    def _build_aliases(self, name: str, tags: List[str]) -> List[str]:
        aliases = {name.lower()}
        for tag in tags:
            for alias in self.ALIAS_GROUPS.get(tag, []):
                aliases.add(alias.lower())
        return sorted(aliases)

    def _build_usage_examples(
        self,
        node: Node,
        query_api: GraphQuery,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        examples: List[Dict[str, Any]] = []
        callers = query_api.get_usage_stats(node).get("used_by_test_cases", [])[: max(limit, 0)]
        for caller in callers:
            test_case_id = caller.get("id")
            test_case_node = query_api.find_node_by_id(test_case_id) if test_case_id else None
            if not test_case_node:
                continue
            examples.append(
                {
                    "test_case_name": caller.get("name"),
                    "test_case_id": caller.get("test_case_id"),
                    "jira_tags": caller.get("jira_tags", []),
                    "feature_file": test_case_node.metadata.file_path,
                    "line_number": test_case_node.metadata.line_number,
                }
            )
        return examples

    def _calculate_stability_score(
        self,
        node: Node,
        stats: Dict[str, Any],
        query_api: GraphQuery,
    ) -> float:
        used_by = stats.get("used_by_test_cases", [])
        if not used_by:
            return 0.0

        weighted_total = 0.0
        weighted_count = 0
        for test_case in used_by:
            test_case_id = test_case.get("id")
            if not test_case_id:
                continue
            tc_node = query_api.find_node_by_id(test_case_id)
            if tc_node is None:
                continue
            history = tc_node.metadata.execution_history or []
            if not history:
                weighted_total += 0.7
                weighted_count += 1
                continue
            total_runs = len(history)
            pass_count = sum(1 for status in history if status == "PASSED")
            ratio = pass_count / total_runs if total_runs else 0.0
            weighted_total += ratio
            weighted_count += 1

        if weighted_count == 0:
            # no history available for dependent tests; assume medium confidence when reused
            return 0.7
        return round(weighted_total / weighted_count, 4)
