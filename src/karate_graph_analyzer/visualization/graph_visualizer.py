import logging
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import quote

from karate_graph_analyzer.models import (
    DependencyGraph, 
    NodeType, 
    Edge, 
    VisualizationMode, 
    DiffStatus
)
# Templates are loaded dynamically in _post_process_html

logger = logging.getLogger(__name__)


class GraphVisualizer:
    """Renders DependencyGraph to an interactive HTML using pyvis."""

    # Standard colors for Default mode
    NODE_COLORS = {
        NodeType.TEST_CASE: "#4CAF50",    # Green
        NodeType.WORKFLOW: "#2196F3",     # Blue
        NodeType.COMMON: "#2196F3",       # Blue
        NodeType.SCENARIO: "#9C27B0",     # Purple
        NodeType.API: "#FF9800",          # Orange (Method)
        NodeType.API_GROUP: "#FF5722",    # Deep Orange (Domain/Path)
        NodeType.PAGE: "#9C27B0",         # Purple
        NodeType.ACTION: "#E91E63",       # Pink
        NodeType.DATABASE: "#F44336",     # Red
        NodeType.DATA: "#795548",         # Brown (Data files)
        NodeType.LOCATOR: "#9E9E9E",      # Grey
        NodeType.JAVASCRIPT: "#F7DF1E",   # JavaScript
        NodeType.JS_FUNCTION: "#F0B429",  # JavaScript function
    }
    NODE_SHAPES = {
        NodeType.TEST_CASE: "star",
        NodeType.WORKFLOW: "square",
        NodeType.COMMON: "square",
        NodeType.SCENARIO: "square",
        NodeType.API: "diamond",
        NodeType.API_GROUP: "hexagon",
        NodeType.PAGE: "ellipse",
        NodeType.ACTION: "triangle",
        NodeType.DATABASE: "database",
        NodeType.DATA: "box",
        NodeType.LOCATOR: "dot",
        NodeType.FOLDER: "hexagon",
        NodeType.FILE: "box",
        NodeType.JAVASCRIPT: "box",
        NodeType.JS_FUNCTION: "dot",
    }

    # --- COMPONENT_REGISTRY (Flow-based mapping) ---
    COMPONENT_REGISTRY = {
        # 1. API Flow (Diamonds/Hexagons)
        "API":          {"shape": "diamond",  "color": "#5c6bc0", "size": 25, "eco": "API Flow"},
        "COMMON":       {"shape": "square",   "color": "#607d8b", "size": 25, "eco": "API Flow"},
        "API_GROUP":    {"shape": "hexagon",  "color": "#3f51b5", "size": 35, "eco": "API Flow"},
        
        # 2. UI Flow (Ellipses/Triangles)
        "PAGE":         {"shape": "ellipse",  "color": "#9c27b0", "size": 25, "eco": "UI Flow"},
        "ACTION":       {"shape": "triangle", "color": "#009688", "size": 20, "eco": "UI Flow"},
        "LOCATOR":      {"shape": "dot",      "color": "#9e9e9e", "size": 15, "eco": "UI Flow"},
        
        # 3. DB Flow (Databases/Dots)
        "DATABASE":     {"shape": "database", "color": "#795548", "size": 22, "eco": "DB Flow"},
        "DB_QUERY":     {"shape": "dot",      "color": "#795548", "size": 11, "eco": "DB Flow"},
        
        # 4. TEST Flow (Stars/Squares)
        "TEST_CASE":    {"shape": "star",     "color": "#03a9f4", "size": 35, "eco": "Test Flow"},
        "SCENARIO":     {"shape": "square",   "color": "#03a9f4", "size": 20, "eco": "Test Flow"},
        "WORKFLOW":     {"shape": "square",   "color": "#03a9f4", "size": 28, "eco": "Test Flow"},
        
        # 5. DATA Flow (Boxes)
        "DATA":         {"shape": "box",      "color": "#00bcd4", "size": 20, "eco": "Data Flow"},

        # 6. Script Flow (Karate JS helpers/config)
        "JAVASCRIPT":   {"shape": "box",      "color": "#f7df1e", "size": 24, "eco": "Script Flow"},
        "JS_FUNCTION":  {"shape": "dot",      "color": "#f0b429", "size": 16, "eco": "Script Flow"},
        
        # 7. Structural Flow (Hierarchy)
        "FOLDER":       {"shape": "hexagon",  "color": "#00897b", "size": 35, "eco": "Structural"},
        "FILE":         {"shape": "box",      "color": "#78909c", "size": 25, "eco": "Structural"},
        
        # Infrastructure
        "DOMAIN":       {"shape": "hexagon",  "color": "#3f51b5", "size": 45, "eco": "Infrastructure"},
    }

    STATUS_COLORS = {
        "PASSED": "#4CAF50",
        "FAILED": "#F44336",
        "PARTIAL_FAIL": "#FF9800",
        "ADDED": "#4CAF50",
        "REMOVED": "#F44336",
        "MODIFIED": "#FF9800",
        "NEUTRAL": "#9E9E9E",
    }

    FIXED_SIZE_NODE_KEYS = {"DATABASE", "DB_QUERY"}
    DEFAULT_VISIBLE_DB_LINK_STATUSES = ("linked", "orphan")
    DB_DEMO_MARKERS = ("example", "examples", "demo", "sample", "fixture")
    DEFAULT_LARGE_GRAPH_THRESHOLD = 1500
    DEFAULT_NODE_LIMIT = 5000
    DEFAULT_EDGE_LIMIT = 12000
    DEFAULT_CHUNK_SIZE = 1000

    def __init__(self, graph: DependencyGraph, mode: VisualizationMode = VisualizationMode.DEFAULT):
        """Initialize visualizer with dependency graph.

        Args:
            graph: Dependency graph to visualize
            mode: Visualization mode (DEFAULT, EXECUTION, or DIFF)
        """
        self.graph = graph
        self.mode = mode
        logger.info(f"Initialized GraphVisualizer for project '{graph.project_name}' in {mode} mode")

    def render(
        self,
        output_path: str = "graph.html",
        height: str = "750px",
        width: str = "100%",
        notebook: bool = False,
        directed: bool = True,
        physics_enabled: Optional[bool] = None,
    ) -> str:
        """Render graph to interactive HTML."""
        # Calculate hotspots before adding elements so tooltips include scores
        self._calculate_hotspots()
        self._visible_node_ids = self._select_visible_node_ids()

        options = self._build_options(physics_enabled)
        payload = self._build_pyvis_payload(options)

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        self._progressive_manifest_tag = self._write_progressive_chunks(output_file)
        self._write_command_center_html(output_file, payload)

        logger.info(f"Graph visualization saved to: {output_file.absolute()}")
        return str(output_file.absolute())

    def _build_options(self, physics_enabled: Optional[bool] = None) -> Dict[str, Any]:
        node_count = len(self.graph.nodes)
        large_graph = node_count >= self._large_graph_threshold()
        resolved_physics = self._resolve_physics_enabled(physics_enabled, large_graph)

        label_draw_threshold = 50 if large_graph else 3
        edge_smooth = False if large_graph else {"type": "cubicBezier", "roundness": 0.5}

        if resolved_physics:
            stabilization_iterations = 80 if large_graph else 200
            options = {
                "physics": {
                    "enabled": True,
                    "forceAtlas2Based": {
                        "gravitationalConstant": -150, "centralGravity": 0.005,
                        "springLength": 250, "springConstant": 0.05, "avoidOverlap": 0.2
                    },
                    "solver": "forceAtlas2Based", "timestep": 0.35,
                    "stabilization": {
                        "enabled": True,
                        "iterations": stabilization_iterations,
                        "updateInterval": 25,
                    }
                }
            }
        else:
            options = {"physics": {"enabled": False}}

        options["interaction"] = {
            "dragNodes": True, "dragView": True, "zoomView": True, "hover": True,
            "navigationButtons": False,
            "keyboard": {"enabled": True, "bindToWindow": False}
        }

        options["nodes"] = {
            "font": {"face": "Outfit", "multi": True},
            "scaling": {
                "min": 15,
                "max": 60,
                "label": {
                    "enabled": True,
                    "min": 14,
                    "max": 50,
                    "maxVisible": 50,
                    "drawThreshold": label_draw_threshold,
                }
            }
        }

        options["edges"] = {
            "smooth": edge_smooth,
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}}
        }
        return options

    def _resolve_physics_enabled(
        self,
        requested: Optional[bool],
        large_graph: bool,
    ) -> bool:
        if requested is not None:
            return requested

        graph_config = getattr(self.graph, "config", None)
        configured = getattr(graph_config, "visualization_physics_enabled", None)
        if configured is not None:
            return bool(configured)

        return not large_graph

    def _large_graph_threshold(self) -> int:
        graph_config = getattr(self.graph, "config", None)
        configured = getattr(graph_config, "visualization_large_graph_threshold", None)
        return int(configured or self.DEFAULT_LARGE_GRAPH_THRESHOLD)

    def _configure_options(self, net: Any, physics_enabled: Optional[bool]):
        """Configure network options including physics and interaction."""
        net.set_options(json.dumps(self._build_options(physics_enabled)))
        
    def _calculate_hotspots(self):
        """Pre-calculate failure hotspots if in EXECUTION mode."""
        self.hotspots = []
        if self.mode == VisualizationMode.EXECUTION:
            try:
                from karate_graph_analyzer.analyzer.dependency_analyzer import DependencyAnalyzer
                analyzer = DependencyAnalyzer(self.graph)
                self.hotspots = analyzer.find_failure_hotspots()
                
                # Update node objects in graph so tooltips and labels can see the data
                for hs in self.hotspots:
                    node = self.graph.nodes.get(hs["node_id"])
                    if node:
                        node.failure_impact_score = hs["failure_impact_score"]
                        node.failure_percentage = hs.get("failure_percentage", 0)
                        node.suggestions = hs.get("suggestions", [])
            except Exception as e:
                logger.error(f"Failed to calculate hotspots: {e}")

    def _add_graph_elements(self, net: Any):
        """Add nodes and edges from the dependency graph using mode-specific coloring."""
        for node in self.graph.nodes.values():
            model = self._build_visual_node_model(node)
            net.add_node(node.id, **self._build_node_attrs(node, model))

        for edge in self.graph.edges.values():
            self._add_graph_edge(net, edge)

        self._highlight_cycles(net)

    def _build_pyvis_payload(self, options: Dict[str, Any]) -> Dict[str, str]:
        """Build the Vis.js payload directly without a temporary PyVis HTML file."""
        nodes = self._build_graph_node_payload()
        edges = self._build_graph_edge_payload({node["id"] for node in nodes})
        self._highlight_cycle_payload_edges(edges)
        return {
            "nodes": json.dumps(nodes, ensure_ascii=False, separators=(",", ":")),
            "edges": json.dumps(edges, ensure_ascii=False, separators=(",", ":")),
            "options": json.dumps(options, ensure_ascii=False, separators=(",", ":")),
        }

    def _build_graph_node_payload(self) -> List[Dict[str, Any]]:
        payload = []
        for node in self.graph.nodes.values():
            if node.id not in self._visible_node_ids:
                continue
            payload.append(self._build_node_payload_item(node))
        return payload

    def _build_graph_edge_payload(self, visible_node_ids: set) -> List[Dict[str, Any]]:
        edge_limit = self._visualization_edge_limit()
        _, outgoing = self._visual_adjacency_maps()
        candidate_edges = []
        seen_edges = set()
        for node_id in visible_node_ids:
            for edge in outgoing.get(node_id, []):
                if edge.id in seen_edges:
                    continue
                if edge.to_node not in visible_node_ids:
                    continue
                seen_edges.add(edge.id)
                candidate_edges.append(edge)

        selected_edges = self._prioritize_edges(candidate_edges)[:edge_limit]
        self._visible_edge_ids = {edge.id for edge in selected_edges}
        return [self._build_edge_payload_item(edge) for edge in selected_edges]

    def _build_node_payload_item(self, node: Any) -> Dict[str, Any]:
        model = self._build_visual_node_model(node)
        attrs = self._build_node_attrs(node, model)
        attrs["id"] = node.id
        return attrs

    def _build_edge_payload_item(self, edge: Edge) -> Dict[str, Any]:
        return {
            "id": edge.id,
            "from": edge.from_node,
            "to": edge.to_node,
            "arrows": "to",
            **self._edge_style(edge),
        }

    def _select_visible_node_ids(self) -> set:
        node_limit = self._visualization_node_limit()
        all_ids = set(self.graph.nodes)
        if node_limit <= 0 or len(all_ids) <= node_limit:
            self._visualization_truncated = False
            return all_ids

        incoming, outgoing = self._visual_adjacency_maps()
        degree = {
            node_id: len(incoming.get(node_id, [])) + len(outgoing.get(node_id, []))
            for node_id in all_ids
        }
        visible: set = set()

        def add_node(node_id: str) -> bool:
            if node_id not in self.graph.nodes or len(visible) >= node_limit:
                return False
            visible.add(node_id)
            return True

        def add_neighborhood(node_id: str, neighbor_limit: int = 12) -> None:
            add_node(node_id)
            neighbors = [
                edge.from_node for edge in incoming.get(node_id, [])
            ] + [
                edge.to_node for edge in outgoing.get(node_id, [])
            ]
            neighbors = sorted(set(neighbors), key=lambda nid: (-degree.get(nid, 0), nid))
            for neighbor_id in neighbors[:neighbor_limit]:
                if len(visible) >= node_limit:
                    return
                add_node(neighbor_id)

        hotspot_ids = [item.get("node_id") for item in getattr(self, "hotspots", []) if item.get("node_id")]
        for node_id in hotspot_ids:
            add_neighborhood(node_id, neighbor_limit=30)

        scored_nodes = self._ordered_visual_nodes(degree)
        for node in scored_nodes:
            if len(visible) >= node_limit:
                break
            if add_node(node.id) and node.type != NodeType.TEST_CASE:
                add_neighborhood(node.id, neighbor_limit=5)

        self._visualization_truncated = True
        logger.warning(
            "Visualization for project '%s' was capped at %d/%d nodes",
            self.graph.project_name,
            len(visible),
            len(all_ids),
        )
        return visible

    def _ordered_visual_nodes(self, degree: Optional[Dict[str, int]] = None) -> List[Any]:
        if degree is None and hasattr(self, "_ordered_visual_nodes_cache"):
            return self._ordered_visual_nodes_cache
        if degree is None:
            degree = self._visual_degree_map()
        ordered = sorted(
            self.graph.nodes.values(),
            key=lambda node: self._visual_node_priority(node, degree.get(node.id, 0)),
        )
        if degree is self._visual_degree_map():
            self._ordered_visual_nodes_cache = ordered
        return ordered

    def _visual_degree_map(self) -> Dict[str, int]:
        if hasattr(self, "_visual_degree"):
            return self._visual_degree

        incoming, outgoing = self._visual_adjacency_maps()
        degree = {
            node_id: len(incoming.get(node_id, [])) + len(outgoing.get(node_id, []))
            for node_id in self.graph.nodes
        }
        self._visual_degree = degree
        return degree

    def _visual_node_priority(self, node: Any, degree: int) -> tuple:
        status_priority = {
            "FAILED": 0,
            "PARTIAL_FAIL": 1,
            "ADDED": 2,
            "MODIFIED": 3,
            "PASSED": 5,
        }.get(node.execution_status or "NEUTRAL", 4)
        type_priority = {
            NodeType.API_GROUP: 0,
            NodeType.API: 1,
            NodeType.DATABASE: 1,
            NodeType.COMMON: 2,
            NodeType.WORKFLOW: 2,
            NodeType.PAGE: 3,
            NodeType.JAVASCRIPT: 3,
            NodeType.JS_FUNCTION: 4,
            NodeType.TEST_CASE: 5,
            NodeType.SCENARIO: 5,
            NodeType.DATA: 6,
            NodeType.LOCATOR: 7,
            NodeType.FILE: 8,
            NodeType.FOLDER: 9,
        }.get(node.type, 10)
        return (status_priority, type_priority, -degree, node.name, node.id)

    def _prioritize_edges(self, edges: List[Edge]) -> List[Edge]:
        return sorted(edges, key=self._visual_edge_priority)

    def _visual_edge_priority(self, edge: Edge) -> tuple:
        from_node = self.graph.nodes.get(edge.from_node)
        to_node = self.graph.nodes.get(edge.to_node)
        failed = any(
            node and node.execution_status in {"FAILED", "PARTIAL_FAIL"}
            for node in (from_node, to_node)
        )
        structural = any(
            node and node.type in {NodeType.FILE, NodeType.FOLDER}
            for node in (from_node, to_node)
        )
        return (0 if failed else 1, 1 if structural else 0, edge.from_node, edge.to_node)

    def _visualization_node_limit(self) -> int:
        graph_config = getattr(self.graph, "config", None)
        configured = getattr(graph_config, "visualization_node_limit", None)
        return int(configured or self.DEFAULT_NODE_LIMIT)

    def _visualization_edge_limit(self) -> int:
        graph_config = getattr(self.graph, "config", None)
        configured = getattr(graph_config, "visualization_edge_limit", None)
        return int(configured or self.DEFAULT_EDGE_LIMIT)

    def _progressive_enabled(self) -> bool:
        graph_config = getattr(self.graph, "config", None)
        configured = getattr(graph_config, "visualization_progressive_enabled", True)
        return bool(configured)

    def _visualization_chunk_size(self) -> int:
        graph_config = getattr(self.graph, "config", None)
        configured = getattr(graph_config, "visualization_chunk_size", None)
        return max(1, int(configured or self.DEFAULT_CHUNK_SIZE))

    def _visualization_auto_load_chunks(self) -> int:
        graph_config = getattr(self.graph, "config", None)
        configured = getattr(graph_config, "visualization_auto_load_chunks", 0)
        return max(0, int(configured or 0))

    def _write_progressive_chunks(self, output_file: Path) -> str:
        if not self._progressive_enabled():
            return ""
        if not getattr(self, "_visualization_truncated", False):
            return ""

        assets_dir = output_file.parent / f"{output_file.stem}.assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        for stale in assets_dir.glob("graph_chunk_*.js"):
            try:
                stale.unlink()
            except OSError:
                pass

        visible_ids = set(getattr(self, "_visible_node_ids", set()))
        ordered_remaining = [
            node.id
            for node in self._ordered_visual_nodes()
            if node.id not in visible_ids
        ]
        if not ordered_remaining:
            return ""

        emitted_edges = set(getattr(self, "_visible_edge_ids", set()))
        loaded_ids = set(visible_ids)
        incoming, outgoing = self._visual_adjacency_maps()
        chunk_size = self._visualization_chunk_size()
        chunks = []

        for chunk_number, start in enumerate(range(0, len(ordered_remaining), chunk_size), start=1):
            chunk_ids = ordered_remaining[start:start + chunk_size]
            chunk_set = set(chunk_ids)
            loaded_ids.update(chunk_set)

            node_payload = []
            metadata_payload = {}
            for node_id in chunk_ids:
                node = self.graph.nodes.get(node_id)
                if not node:
                    continue
                node_payload.append(self._build_node_payload_item(node))
                metadata_payload[node_id] = self._build_js_metadata_entry(node_id, node)

            candidate_edges = []
            seen_candidate_edges = set()
            for node_id in chunk_set:
                for edge in outgoing.get(node_id, []):
                    if edge.id not in seen_candidate_edges:
                        candidate_edges.append(edge)
                        seen_candidate_edges.add(edge.id)
                for edge in incoming.get(node_id, []):
                    if edge.id not in seen_candidate_edges:
                        candidate_edges.append(edge)
                        seen_candidate_edges.add(edge.id)

            edge_payload = []
            for edge in self._prioritize_edges(candidate_edges):
                if edge.id in emitted_edges:
                    continue
                if edge.from_node not in loaded_ids or edge.to_node not in loaded_ids:
                    continue
                links_new_nodes = edge.from_node in chunk_set or edge.to_node in chunk_set
                if not links_new_nodes:
                    continue
                edge_payload.append(self._build_edge_payload_item(edge))
                emitted_edges.add(edge.id)

            chunk_file = assets_dir / f"graph_chunk_{chunk_number:04d}.js"
            chunk_data = {
                "index": chunk_number,
                "nodes": node_payload,
                "edges": edge_payload,
                "metadata": metadata_payload,
            }
            chunk_file.write_text(
                "window.__KG_LOAD_CHUNK__ && window.__KG_LOAD_CHUNK__("
                + json.dumps(chunk_data, ensure_ascii=False, separators=(",", ":"))
                + ");\n",
                encoding="utf-8",
            )
            chunks.append(
                {
                    "index": chunk_number,
                    "path": f"{assets_dir.name}/{chunk_file.name}",
                    "nodes": len(node_payload),
                    "edges": len(edge_payload),
                }
            )

        manifest_path = assets_dir / "manifest.js"
        manifest = {
            "enabled": True,
            "total_nodes": len(self.graph.nodes),
            "total_edges": len(self.graph.edges),
            "initial_nodes": len(visible_ids),
            "initial_edges": len(getattr(self, "_visible_edge_ids", set())),
            "chunk_size": chunk_size,
            "auto_load_chunks": self._visualization_auto_load_chunks(),
            "chunks": chunks,
        }
        manifest_path.write_text(
            "window.KG_PROGRESSIVE_MANIFEST="
            + json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
            + ";\nwindow.dispatchEvent(new CustomEvent('kg-progressive-manifest-ready'));\n",
            encoding="utf-8",
        )

        manifest_url = quote(f"{assets_dir.name}/{manifest_path.name}", safe="/")
        logger.info(
            "Progressive visualization generated %d chunks in %s",
            len(chunks),
            assets_dir,
        )
        return f'<script type="text/javascript" src="{manifest_url}"></script>'

    def _highlight_cycle_payload_edges(self, edge_payload: List[Dict[str, Any]]) -> None:
        edge_lookup: Dict[tuple, List[Dict[str, Any]]] = {}
        for edge in edge_payload:
            edge_lookup.setdefault((edge["from"], edge["to"]), []).append(edge)

        for cycle in self.graph.cycles:
            for i in range(len(cycle)):
                from_n, to_n = cycle[i], cycle[(i + 1) % len(cycle)]
                for edge in edge_lookup.get((from_n, to_n), []):
                    edge.update({"color": "#FF0000", "width": 3, "title": "CYCLE DETECTED"})

    def _resolve_registry_key(self, node: Any) -> str:
        reg_key = node.type.value if hasattr(node.type, 'value') else str(node.type)

        if reg_key == "DATABASE" and node.metadata.additional_data.get("scenario_tag"):
            return "DB_QUERY"

        if reg_key in self.COMPONENT_REGISTRY:
            return reg_key
        if reg_key in ["ACTION", "SCENARIO", "WORKFLOW"]:
            return "TEST_CASE"
        return "SCENARIO"

    def _build_visual_node_model(self, node: Any) -> Dict[str, Any]:
        reg_key = self._resolve_registry_key(node)
        config = self.COMPONENT_REGISTRY[reg_key]
        ecosystem = config["eco"]
        test_case_id = self._get_primary_test_case_id(node)
        display_name = self._format_node_display_name(node, reg_key)

        details_copy = node.metadata.additional_data.copy()
        details_copy.pop("display_data", None)
        if node.type == NodeType.DATABASE:
            details_copy.update(self._db_link_context(node))

        display_data = {
            "id": node.id,
            "name": node.name,
            "display_name": display_name,
            "test_case_id": test_case_id,
            "type_label": reg_key,
            "flow": ecosystem,
            "file_path": node.metadata.file_path,
            "line_number": node.metadata.line_number,
            "status": node.execution_status or "NEUTRAL",
            "badges": [ecosystem, reg_key],
            "jira_tags": node.metadata.jira_tags,
            "expert_notes": node.metadata.expert_notes,
            "suggestions": node.metadata.suggestions,
            "execution_history": node.metadata.execution_history,
            "execution_runs": node.metadata.additional_data.get("execution_runs", []),
            "failure_fingerprint": node.metadata.additional_data.get("failure_fingerprint"),
            "failure_category": node.metadata.additional_data.get("failure_category"),
            "last_run": node.metadata.additional_data.get("last_run"),
            "last_artifacts": node.metadata.additional_data.get("last_artifacts", []),
            "details": details_copy
        }

        domain = node.metadata.additional_data.get('domain')
        if domain:
            display_data["badges"].append(domain)

        node.metadata.additional_data["display_data"] = display_data
        node.metadata.additional_data["reg_key"] = reg_key
        node.metadata.additional_data["eco"] = ecosystem

        return {
            "reg_key": reg_key,
            "config": config,
            "ecosystem": ecosystem,
            "display_name": display_name,
            "test_case_id": test_case_id,
        }

    def _db_link_context(self, node: Any) -> Dict[str, Any]:
        kind = self._db_node_kind(node)
        usage = self._usage_stats_for_node(node)
        used_by = usage.get("used_by_test_cases", [])
        if used_by:
            status = "linked"
            reason = "Reachable from at least one terminal test case."
        elif kind == "component":
            status = "component"
            reason = "DB feature/helper component kept for structure and reuse context."
        elif self._is_demo_db_node(node):
            status = "demo"
            reason = "Example/demo DB flow, not counted as execution impact."
        else:
            status = "orphan"
            reason = "Query has no upstream terminal test case."

        return {
            "db_kind": kind,
            "link_status": status,
            "link_status_reason": reason,
            "usage_count": usage.get("usage_count", 0),
            "default_visible_link_statuses": list(self.DEFAULT_VISIBLE_DB_LINK_STATUSES),
        }

    def _db_node_kind(self, node: Any) -> str:
        data = node.metadata.additional_data or {}
        if any(
            [
                data.get("operation"),
                data.get("table"),
                data.get("database"),
                data.get("host"),
                data.get("entity_name"),
                data.get("dialect") and data.get("dialect") != "unknown",
            ]
        ):
            return "query"
        return "component"

    def _usage_stats_for_node(self, node: Any) -> Dict[str, Any]:
        if not hasattr(self, "_graph_query"):
            from karate_graph_analyzer.graph.graph_query import GraphQuery

            self._graph_query = GraphQuery(self.graph)
        return self._graph_query.get_usage_stats(node, test_case_limit=25)

    def _is_demo_db_node(self, node: Any) -> bool:
        text = " ".join(self._node_context_terms(node)).lower()
        return any(marker in text for marker in self.DB_DEMO_MARKERS)

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

        seen = {node.id}
        frontier = [node.id]
        incoming_edges = self._incoming_edge_map()
        for _ in range(max_depth):
            next_frontier = []
            for target in frontier:
                for edge in incoming_edges.get(target, []):
                    if edge.from_node in seen:
                        continue
                    seen.add(edge.from_node)
                    parent = self.graph.nodes.get(edge.from_node)
                    if not parent:
                        continue
                    parent_data = parent.metadata.additional_data or {}
                    terms.extend(
                        [
                            parent.name,
                            str(parent.metadata.file_path or ""),
                            " ".join(parent.tags or []),
                            " ".join(parent.metadata.jira_tags or []),
                            str(parent_data.get("scenario_name", "")),
                            " ".join(parent_data.get("scenario_tags", []) or []),
                            str(parent_data.get("workflow_path", "")),
                        ]
                    )
                    next_frontier.append(edge.from_node)
            frontier = next_frontier
            if not frontier:
                break
        return terms

    def _incoming_edge_map(self) -> Dict[str, List[Edge]]:
        incoming, _ = self._visual_adjacency_maps()
        return incoming

    def _visual_adjacency_maps(self) -> tuple[Dict[str, List[Edge]], Dict[str, List[Edge]]]:
        if hasattr(self, "_visual_incoming_edges") and hasattr(self, "_visual_outgoing_edges"):
            return self._visual_incoming_edges, self._visual_outgoing_edges

        incoming: Dict[str, List[Edge]] = {}
        outgoing: Dict[str, List[Edge]] = {}
        for edge in self.graph.edges.values():
            incoming.setdefault(edge.to_node, []).append(edge)
            outgoing.setdefault(edge.from_node, []).append(edge)
        self._visual_incoming_edges = incoming
        self._visual_outgoing_edges = outgoing
        return incoming, outgoing

    def _get_primary_test_case_id(self, node: Any) -> Optional[str]:
        if not node.metadata.jira_tags:
            return None
        return node.metadata.jira_tags[0].lstrip("@")

    def _format_node_display_name(self, node: Any, reg_key: str) -> str:
        test_case_id = self._get_primary_test_case_id(node)
        if not test_case_id or reg_key not in {"TEST_CASE", "SCENARIO", "ACTION"}:
            return node.name

        clean_name = re.sub(rf"^@?{re.escape(test_case_id)}\s*[-:|]?\s*", "", node.name).strip()
        return f"@{test_case_id} - {clean_name or node.name}"

    def _is_terminal_visual_node(self, reg_key: str) -> bool:
        return reg_key in {"TEST_CASE", "SCENARIO", "ACTION", "API", "DATABASE"}

    def _status_node_style(self, node: Any, reg_key: str, base_color: str) -> Dict[str, Any]:
        status_color = self.STATUS_COLORS.get(node.execution_status, base_color)
        if self._is_terminal_visual_node(reg_key):
            return {
                "background": status_color,
                "border": status_color,
                "border_width": 2,
            }

        return {
            "background": "#ffffff",
            "border": status_color,
            "border_width": 4 if node.execution_status != 'PASSED' else 2,
        }

    def _build_node_attrs(self, node: Any, model: Dict[str, Any]) -> Dict[str, Any]:
        reg_key = model["reg_key"]
        config = model["config"]
        style = self._status_node_style(node, reg_key, config["color"])
        fail_count = node.execution_details.get("failed_count", 0)
        is_terminal = self._is_terminal_visual_node(reg_key)

        display_label = model["display_name"]
        label_font_size = 14
        if fail_count > 0 and is_terminal:
            display_label = f"[{fail_count} FAIL]\n{model['display_name']}"
            label_font_size = 14 + min(fail_count, 15)

        node_attrs = {
            "label": display_label,
            "shape": config["shape"],
            "color": {
                "background": style["background"],
                "border": style["border"],
                "highlight": {"background": style["background"], "border": style["border"]},
            },
            "borderWidth": style["border_width"],
            "size": config["size"],
            "font": {
                "size": label_font_size,
                "color": "#2c3e50",
                "face": "Inter, system-ui",
                "multi": True,
                "bold": node.execution_status != 'PASSED'
            },
            "mass": 5 if model["ecosystem"] == "Infrastructure" else 1,
            "title": self._build_tooltip(node)
        }

        if fail_count > 0 and reg_key not in self.FIXED_SIZE_NODE_KEYS:
            node_attrs["value"] = 10 + (fail_count * 5)

        return node_attrs

    def _edge_style(self, edge: Edge) -> Dict[str, Any]:
        color = "#808080"
        width = 1
        dashes = False

        if self.mode == VisualizationMode.EXECUTION:
            to_node = self.graph.nodes.get(edge.to_node)
            if to_node and to_node.execution_status == "FAILED":
                color = self.STATUS_COLORS["FAILED"]
                width = 4
            elif to_node and to_node.execution_status == "PASSED":
                color = self.STATUS_COLORS["PASSED"]
                width = 3
            else:
                color = self.STATUS_COLORS["NEUTRAL"]

        elif self.mode == VisualizationMode.DIFF:
            if edge.diff_status == DiffStatus.ADDED:
                color = self.STATUS_COLORS["ADDED"]
                width = 3
            elif edge.diff_status == DiffStatus.REMOVED:
                color = self.STATUS_COLORS["REMOVED"]
                width = 3
                dashes = True
            else:
                color = self.STATUS_COLORS["NEUTRAL"]

        else:
            edge_type_colors = {
                "WORKFLOW": "#2196F3",
                "API": "#FF9800",
                "PAGE": "#9C27B0",
                "DATABASE": "#F44336"
            }
            color = edge_type_colors.get(edge.type.value, "#808080")

        return {"color": color, "width": width, "dashes": dashes}

    def _add_graph_edge(self, net: Any, edge: Edge):
        if edge.from_node not in net.get_nodes() or edge.to_node not in net.get_nodes():
            logger.warning(f"Skipping edge {edge.from_node} -> {edge.to_node}: One or both nodes missing in visualizer")
            return

        style = self._edge_style(edge)
        net.add_edge(edge.from_node, edge.to_node, arrows="to", **style)

    def _highlight_cycles(self, net: Any):
        for cycle in self.graph.cycles:
            for i in range(len(cycle)):
                from_n, to_n = cycle[i], cycle[(i + 1) % len(cycle)]
                for edge in net.edges:
                    if edge["from"] == from_n and edge["to"] == to_n:
                        edge.update({"color": "#FF0000", "width": 3, "title": "CYCLE DETECTED"})

    def _build_tooltip(self, node: Any) -> str:
        # Get pre-calculated identity from loop
        reg_key = node.metadata.additional_data.get("reg_key", node.type.value)
        ecosystem = node.metadata.additional_data.get("eco", "Unknown")
        
        parts = [
            f"<div style='font-size:14px; margin-bottom:5px;'><b>{self._format_node_display_name(node, reg_key)}</b></div>",
            f"<div style='margin-bottom:8px;'><span style='background:#eee; padding:2px 6px; border-radius:4px; font-size:10px;'>{ecosystem}</span> <b style='color:#666;'>{reg_key}</b></div>",
            f"<div style='font-size:11px; color:#888;'>ID: {node.id}</div>"
        ]
        test_case_id = self._get_primary_test_case_id(node)
        if test_case_id:
            parts.append(f"<div style='font-size:11px; color:#1565c0;'><b>Test Case:</b> @{test_case_id}</div>")
        if node.metadata.file_path: 
            parts.append(f"<div style='font-size:11px; color:#888;'><b>File:</b> {node.metadata.file_path}</div>")
        
        # Add API specific info
        if node.type == NodeType.API_GROUP:
            level = node.metadata.additional_data.get("level")
            if level is not None:
                parts.append(f"<b>Hierarchy Level:</b> {level}")
            
            phys_url = node.metadata.additional_data.get("physical_url")
            if phys_url:
                parts.append(f"<b>Physical URL:</b> {phys_url}")
                
        if node.metadata.jira_tags: parts.append(f"<b>Jira:</b> {', '.join(node.metadata.jira_tags)}")
        clean_tags = [t for t in node.tags if not (t.startswith("@ALM2:") or t == "@ignore")]
        if clean_tags: parts.append(f"<b>Tags:</b> {', '.join(clean_tags)}")
        
        # Add Failure Impact Score if available
        if hasattr(node, 'failure_impact_score') and node.failure_impact_score > 0:
            parts.append(f"<hr><b style='color:#F44336;'>🔥 Failure Impact Score: {node.failure_impact_score}</b>")
            parts.append(f"<span style='font-size:11px; color:#666;'>Contributes to {node.failure_impact_score} test failures</span>")
            
        return "<br>".join(parts)

    def _write_command_center_html(
        self,
        output_file: Path,
        pyvis_payload: Dict[str, str],
    ) -> None:
        from karate_graph_analyzer.visualization.templates import (
            LAYOUT_TEMPLATE,
            GRAPH_STYLE,
            GRAPH_JS_SCRIPT
        )

        final_html = self._assemble_command_center_html(
            LAYOUT_TEMPLATE,
            GRAPH_STYLE,
            GRAPH_JS_SCRIPT,
            pyvis_payload,
        )
        output_file.write_text(final_html, encoding='utf-8')

    def _post_process_html(self, output_file: Path):
        """Transform generated HTML into a Professional Command Center."""
        from karate_graph_analyzer.visualization.templates import (
            LAYOUT_TEMPLATE,
            GRAPH_STYLE,
            GRAPH_JS_SCRIPT
        )

        raw_content = output_file.read_text(encoding='utf-8')
        payload = self._extract_pyvis_payload(raw_content)
        final_html = self._assemble_command_center_html(
            LAYOUT_TEMPLATE,
            GRAPH_STYLE,
            GRAPH_JS_SCRIPT,
            payload,
        )

        output_file.write_text(final_html, encoding='utf-8')

    def _build_js_metadata(self) -> Dict[str, Any]:
        js_data = {}
        visible_node_ids = getattr(self, "_visible_node_ids", set(self.graph.nodes))
        for node_id, node in self.graph.nodes.items():
            if node_id not in visible_node_ids:
                continue
            js_data[node_id] = self._build_js_metadata_entry(node_id, node)
        return js_data

    def _build_js_metadata_entry(self, node_id: str, node: Any) -> Dict[str, Any]:
        return {
            "id": node_id,
            "name": node.name,
            "type": node.type.value if hasattr(node.type, 'value') else str(node.type),
            "execution_status": node.execution_status,
            "execution_details": node.execution_details,
            "additional_data": node.metadata.additional_data,
            "environment_variants": node.metadata.environment_variants
        }

    def _extract_pyvis_payload(self, raw_content: str) -> Dict[str, str]:
        nodes_match = re.search(r'nodes = new vis\.DataSet\(\s*(\[.*?\])\s*\);', raw_content, re.DOTALL)
        edges_match = re.search(r'edges = new vis\.DataSet\(\s*(\[.*?\])\s*\);', raw_content, re.DOTALL)
        options_match = re.search(r'var options = (\{.*?\});', raw_content, re.DOTALL)

        return {
            "nodes": nodes_match.group(1) if nodes_match else "[]",
            "edges": edges_match.group(1) if edges_match else "[]",
            "options": options_match.group(1) if options_match else "{}",
        }

    def _build_global_vars(self) -> Dict[str, Any]:
        global_vars = {}
        if not (hasattr(self.graph, 'config') and self.graph.config):
            return global_vars

        global_vars = self.graph.config.base_url_mapping or {}
        if self.graph.config.env_url_mapping:
            for env, mapping in self.graph.config.env_url_mapping.items():
                for k, v in mapping.items():
                    global_vars[f"{env}:{k}"] = v

        return global_vars

    def _get_jira_base_url(self) -> str:
        if hasattr(self.graph, 'config') and self.graph.config:
            return self.graph.config.jira_base_url or ""
        return ""

    def _assemble_command_center_html(
        self,
        layout_template: str,
        graph_style: str,
        graph_script: str,
        pyvis_payload: Dict[str, str],
    ) -> str:
        final_html = layout_template.replace("{{STYLE_INJECTION}}", graph_style)
        final_html = final_html.replace("{{SCRIPT_INJECTION}}", graph_script)
        final_html = final_html.replace("{{GRAPH_NODES}}", pyvis_payload["nodes"])
        final_html = final_html.replace("{{GRAPH_EDGES}}", pyvis_payload["edges"])
        final_html = final_html.replace(
            "{{METADATA}}",
            json.dumps(self._build_js_metadata(), ensure_ascii=False, separators=(",", ":")),
        )
        final_html = final_html.replace(
            "{{HOTSPOTS}}",
            json.dumps(getattr(self, 'hotspots', []), ensure_ascii=False, separators=(",", ":")),
        )
        final_html = final_html.replace(
            "{{ENV_VARS}}",
            json.dumps(self._build_global_vars(), ensure_ascii=False, separators=(",", ":")),
        )
        final_html = final_html.replace("{{MODE}}", self.mode.value)
        final_html = final_html.replace("{{JIRA_URL}}", self._get_jira_base_url())
        final_html = final_html.replace("{{OPTIONS}}", pyvis_payload["options"])
        final_html = final_html.replace(
            "{{PROGRESSIVE_MANIFEST_TAG}}",
            getattr(self, "_progressive_manifest_tag", ""),
        )
        return final_html

    # _add_legend is now handled in _post_process_html

    def get_statistics(self) -> Dict[str, Any]:
        from collections import Counter
        return {
            "total_nodes": len(self.graph.nodes),
            "total_edges": len(self.graph.edges),
            "node_counts": Counter(node.type.value for node in self.graph.nodes.values()),
            "cycles_detected": len(self.graph.cycles),
            "project_name": self.graph.project_name,
        }

    def render_subgraph(self, node_ids: List[str], output_path: str = "subgraph.html", **kwargs) -> str:
        from karate_graph_analyzer.models import DependencyGraph
        subgraph = DependencyGraph(
            project_name=f"{self.graph.project_name}_subgraph",
            nodes={nid: n for nid, n in self.graph.nodes.items() if nid in node_ids},
            edges={eid: e for eid, e in self.graph.edges.items() if e.from_node in node_ids and e.to_node in node_ids},
            cycles=[]
        )
        return GraphVisualizer(subgraph).render(output_path, **kwargs)

    def render_impact_view(self, changed_component_id: str, affected_test_case_ids: List[str], output_path: str = "impact_view.html", **kwargs) -> str:
        """Render impact analysis view highlighting affected components."""
        try:
            from pyvis.network import Network
        except ImportError:
            raise ImportError("pyvis is required for visualization")

        net = Network(height=kwargs.get("height", "750px"), width=kwargs.get("width", "100%"), directed=True)
        
        for node in self.graph.nodes.values():
            color = self.NODE_COLORS.get(node.type, "#808080")
            size, border_width = 25, 1
            
            if node.id == changed_component_id:
                color, size, border_width = "#FF0000", 40, 5
            elif node.id in affected_test_case_ids:
                color, size, border_width = "#FFA500", 30, 3

            net.add_node(node.id, label=node.name, title=self._build_tooltip(node), color=color, 
                         shape=self.NODE_SHAPES.get(node.type, "dot"), size=size, borderWidth=border_width)

        for edge in self.graph.edges.values():
            net.add_edge(edge.from_node, edge.to_node, arrows="to")

        output_file = Path(output_path)
        net.save_graph(str(output_file))
        self._post_process_html(output_file)
        return str(output_file.absolute())
