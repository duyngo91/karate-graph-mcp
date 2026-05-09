import logging
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

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
        "DATABASE":     {"shape": "database", "color": "#795548", "size": 30, "eco": "DB Flow"},
        "DB_QUERY":     {"shape": "dot",      "color": "#795548", "size": 15, "eco": "DB Flow"},
        
        # 4. TEST Flow (Stars/Squares)
        "TEST_CASE":    {"shape": "star",     "color": "#03a9f4", "size": 35, "eco": "Test Flow"},
        "SCENARIO":     {"shape": "square",   "color": "#03a9f4", "size": 20, "eco": "Test Flow"},
        "WORKFLOW":     {"shape": "square",   "color": "#03a9f4", "size": 28, "eco": "Test Flow"},
        
        # 5. DATA Flow (Boxes)
        "DATA":         {"shape": "box",      "color": "#00bcd4", "size": 20, "eco": "Data Flow"},
        
        # 6. Structural Flow (Hierarchy)
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
        physics_enabled: bool = True,
    ) -> str:
        """Render graph to interactive HTML."""
        try:
            from pyvis.network import Network
        except ImportError:
            raise ImportError("pyvis is required for visualization. pip install pyvis")

        net = Network(height=height, width=width, notebook=notebook, directed=directed)
        self._configure_options(net, physics_enabled)
        
        # Calculate hotspots before adding elements so tooltips include scores
        self._calculate_hotspots()
        
        self._add_graph_elements(net)
        # Legend is now handled in _post_process_html

        output_file = Path(output_path)
        net.save_graph(str(output_file))
        self._post_process_html(output_file)

        logger.info(f"Graph visualization saved to: {output_file.absolute()}")
        return str(output_file.absolute())

    def _configure_options(self, net: Any, physics_enabled: bool):
        """Configure network options including physics and interaction."""
        if physics_enabled:
            options = {
                "physics": {
                    "enabled": True,
                    "forceAtlas2Based": {
                        "gravitationalConstant": -150, "centralGravity": 0.005,
                        "springLength": 250, "springConstant": 0.05, "avoidOverlap": 0.2
                    },
                    "solver": "forceAtlas2Based", "timestep": 0.35,
                    "stabilization": {"enabled": True, "iterations": 200, "updateInterval": 25}
                }
            }
        else:
            options = {"physics": {"enabled": False}}
        
        options["interaction"] = {
            "dragNodes": True, "dragView": True, "zoomView": True, "hover": True,
            "navigationButtons": False, # Hide redundant buttons
            "keyboard": {"enabled": True, "bindToWindow": False}
        }

        # Failure-based Scaling & Label visibility
        options["nodes"] = {
            "font": {"face": "Outfit", "multi": True},
            "scaling": {
                "min": 15,
                "max": 60,
                "label": {
                    "enabled": True,
                    "min": 14,
                    "max": 50, # Support very large text for zoom-out
                    "maxVisible": 50,
                    "drawThreshold": 3 # Show labels even when nodes are tiny
                }
            }
        }
        
        options["edges"] = {
            "smooth": {"type": "cubicBezier", "roundness": 0.5},
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}}
        }
        
        net.set_options(json.dumps(options))
        
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

        details_copy = node.metadata.additional_data.copy()
        details_copy.pop("display_data", None)

        display_data = {
            "id": node.id,
            "name": node.name,
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
        }

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

        display_label = node.name
        label_font_size = 14
        if fail_count > 0 and is_terminal:
            display_label = f"[{fail_count} FAIL]\n{node.name}"
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

        if fail_count > 0:
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
            f"<div style='font-size:14px; margin-bottom:5px;'><b>{node.name}</b></div>",
            f"<div style='margin-bottom:8px;'><span style='background:#eee; padding:2px 6px; border-radius:4px; font-size:10px;'>{ecosystem}</span> <b style='color:#666;'>{reg_key}</b></div>",
            f"<div style='font-size:11px; color:#888;'>ID: {node.id}</div>"
        ]
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
        for node_id, node in self.graph.nodes.items():
            js_data[node_id] = {
                "id": node_id,
                "name": node.name,
                "type": node.type.value if hasattr(node.type, 'value') else str(node.type),
                "execution_status": node.execution_status,
                "execution_details": node.execution_details,
                "additional_data": node.metadata.additional_data,
                "environment_variants": node.metadata.environment_variants
            }
        return js_data

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
        final_html = final_html.replace("{{METADATA}}", json.dumps(self._build_js_metadata()))
        final_html = final_html.replace("{{HOTSPOTS}}", json.dumps(getattr(self, 'hotspots', [])))
        final_html = final_html.replace("{{ENV_VARS}}", json.dumps(self._build_global_vars()))
        final_html = final_html.replace("{{MODE}}", self.mode.value)
        final_html = final_html.replace("{{JIRA_URL}}", self._get_jira_base_url())
        final_html = final_html.replace("{{OPTIONS}}", pyvis_payload["options"])
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
