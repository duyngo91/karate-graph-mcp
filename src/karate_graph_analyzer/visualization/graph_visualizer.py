import logging
import json
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

    # --- COMPONENT REGISTRY (3 Ecosystems: Infrastructure, Library, Execution) ---
    COMPONENT_REGISTRY = {
        # 1. INFRASTRUCTURE (Indigo Hexagons)
        "DOMAIN":       {"shape": "hexagon",  "color": "#3f51b5", "size": 45, "eco": "Infrastructure"},
        "API_GROUP":    {"shape": "hexagon",  "color": "#3f51b5", "size": 35, "eco": "Infrastructure"},
        
        # 2. LIBRARY (Blue Grey Squares/Diamonds)
        "COMMON":       {"shape": "square",   "color": "#607d8b", "size": 25, "eco": "Library"},
        "UTILITY":      {"shape": "diamond",  "color": "#607d8b", "size": 20, "eco": "Library"},
        
        # 3. EXECUTION (Blue Stars/Diamonds)
        "API":          {"shape": "diamond",  "color": "#5c6bc0", "size": 25, "eco": "Execution"},
        "TEST_CASE":    {"shape": "star",     "color": "#03a9f4", "size": 35, "eco": "Execution"},
        "SCENARIO":     {"shape": "star",     "color": "#03a9f4", "size": 25, "eco": "Execution"},
        "ACTION":       {"shape": "triangle", "color": "#009688", "size": 20, "eco": "Execution"},
        "WORKFLOW":     {"shape": "star",     "color": "#03a9f4", "size": 30, "eco": "Execution"},
        
        # Others
        "PAGE":         {"shape": "ellipse",  "color": "#9c27b0", "size": 25, "eco": "UI Objects"},
        "DATABASE":     {"shape": "database", "color": "#795548", "size": 30, "eco": "Storage"},
        "DATA":         {"shape": "box",      "color": "#00bcd4", "size": 20, "eco": "Data"},
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
        # 1. Add Nodes
        for node in self.graph.nodes.values():
            # Resolve Component Identity
            node_type_str = node.type.value if hasattr(node.type, 'value') else str(node.type)
            
            # --- NEW DESIGN: Strategy-Based Identity Resolution ---
            # 1. Prepare Node Context (to avoid redundant string processing)
            ctx = {
                "name": str(node.name).lower(),
                "id": str(node.id).lower().replace("\\", "/"),
                "path": str(node.metadata.file_path or "").lower().replace("\\", "/"),
                "type": node_type_str,
                "orig_expr": str(node.metadata.additional_data.get("original_expression", "")).lower().replace("\\", "/"),
                "phys_path": str(node.metadata.additional_data.get("physical_path", "")).lower().replace("\\", "/")
            }
            
            # Helper: Is this node in a library folder?
            lib_kws = ["common", "ecommerce", "services", "utils", "lib/", "db/", "web/pages/"]
            ctx["is_lib"] = any(kw in f"{ctx['id']} | {ctx['path']} | {ctx['orig_expr']}" for kw in lib_kws)
            
            # Helper: Is this a file node (.feature and no @) or a call node (@)?
            ctx["is_file"] = ".feature" in ctx["name"] or (".feature" in ctx["path"] and "@" not in ctx["name"])
            ctx["is_call"] = "@" in ctx["name"] or "@" in ctx["id"] or "@" in ctx["orig_expr"]

            # 2. Define Prioritized Identity Rules (Strategy Chain)
            # The first rule that returns a non-None key wins.
            identity_rules = [
                # Rule 1: Library Tier
                lambda c: "COMMON" if c["is_lib"] and c["is_file"] and "@" not in c["name"] else None,
                lambda c: "UTILITY" if c["is_lib"] and c["is_call"] else None,
                lambda c: "UTILITY" if c["is_lib"] and c["type"] in ["SCENARIO", "ACTION", "WORKFLOW"] else None,
                
                # Rule 2: Infrastructure Tier
                lambda c: c["type"] if c["type"] in ["DOMAIN", "API_GROUP", "DATABASE", "DATA"] else None,
                
                # Rule 3: Execution Tier
                lambda c: "COMMON" if c["type"] == "COMMON" else None,
                lambda c: "SCENARIO" if c["is_call"] or c["type"] in ["SCENARIO", "TEST_CASE", "WORKFLOW"] else None,
                
                # Fallback: Use original type if in registry, else default to SCENARIO
                lambda c: c["type"] if c["type"] in self.COMPONENT_REGISTRY else "SCENARIO"
            ]

            # 3. Resolve reg_key
            reg_key = "SCENARIO"
            for rule in identity_rules:
                resolved = rule(ctx)
                if resolved:
                    reg_key = resolved
                    break
            
            # Get configuration from Registry
            config = self.COMPONENT_REGISTRY.get(reg_key, self.COMPONENT_REGISTRY.get("SCENARIO"))
            
            shape = config["shape"]
            base_color = config["color"]
            size = config["size"]
            ecosystem = config["eco"]
            
            # Update node metadata for Tooltips, HUD and JSON export
            node.metadata.additional_data["reg_key"] = reg_key
            node.metadata.additional_data["eco"] = ecosystem
            
            mass = 5 if ecosystem == "Infrastructure" else 1
            is_terminal = ecosystem == "Execution" or reg_key == "UTILITY"

            # Status & Failure Propagation
            fail_count = node.execution_details.get("failed_count", 0)
            status_color = self.STATUS_COLORS.get(node.execution_status, base_color)
            
            border_width = 1
            border_color = "#2c3e50"
            background_color = base_color

            if is_terminal:
                background_color = status_color
                border_color = status_color
                border_width = 2
            else:
                # Structural nodes (Infrastructure/Library): White background, status-colored border
                background_color = "#ffffff"
                border_color = status_color
                border_width = 4 if node.execution_status != 'PASSED' else 2
                
            # Node metadata for frontend
            node.metadata.additional_data["eco"] = ecosystem
            node.metadata.additional_data["reg_key"] = reg_key
            


            # Enhance label for failed nodes (Only for Terminal Nodes to avoid confusion)
            display_label = node.name
            label_font_size = 14
            
            # Only show [X FAIL] on the actual failure points, not the parents
            if fail_count > 0 and is_terminal:
                display_label = f"[{fail_count} FAIL]\n{node.name}"
                label_font_size = 14 + min(fail_count, 15)
            elif node.execution_status != 'PASSED' and not is_terminal:
                # Structural nodes just get a subtle hint if they are hotspots
                # display_label = f"⚠ {node.name}" # Optional: add a warning icon instead of text
                pass

            node_attrs = {
                "label": display_label,
                "shape": shape,
                "color": {
                    "background": background_color,
                    "border": border_color,
                    "highlight": {"background": background_color, "border": border_color},
                },
                "borderWidth": border_width,
                "size": size,
                "font": {
                    "size": label_font_size,
                    "color": "#2c3e50",
                    "face": "Inter, system-ui",
                    "multi": True,
                    "bold": node.execution_status != 'PASSED'
                },
                "mass": mass,
                "title": self._build_tooltip(node)
            }

            # Add scaling by failure impact
            if fail_count > 0:
                node_attrs["value"] = 10 + (fail_count * 5)

            net.add_node(node.id, **node_attrs)

        # 2. Add Edges with Sync Colors (Idea #1 & #2 "Full Path")
        for edge in self.graph.edges.values():
            to_node = self.graph.nodes.get(edge.to_node)
            from_node = self.graph.nodes.get(edge.from_node)
            
            color = "#808080" # Default grey line
            width = 1
            dashes = False
            
            if self.mode == VisualizationMode.EXECUTION:
                # Line color follows the result of the source/target context
                if to_node and to_node.execution_status == "FAILED":
                    color = self.STATUS_COLORS["FAILED"]
                    width = 4 # Significantly thicker
                elif to_node and to_node.execution_status == "PASSED":
                    color = self.STATUS_COLORS["PASSED"]
                    width = 3 # Thicker than default
                else:
                    color = self.STATUS_COLORS["NEUTRAL"]
                    width = 1
            
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
                    width = 1
            
            else: # DEFAULT Mode
                edge_type_colors = {"WORKFLOW": "#2196F3", "API": "#FF9800", "PAGE": "#9C27B0", "DATABASE": "#F44336"}
                color = edge_type_colors.get(edge.type.value, "#808080")

            net.add_edge(edge.from_node, edge.to_node, color=color, width=width, arrows="to", dashes=dashes)

        for cycle in self.graph.cycles:
            for i in range(len(cycle)):
                from_n, to_n = cycle[i], cycle[(i + 1) % len(cycle)]
                for edge in net.edges:
                    if edge["from"] == from_n and edge["to"] == to_n:
                        edge.update({"color": "#FF0000", "width": 3, "title": "⚠️ CYCLE DETECTED"})

    def _get_display_label(self, name: str) -> str:
        if len(name) > 30 and ("/" in name or "\\" in name):
            parts = name.replace("\\", "/").split("/")
            return ".../" + "/".join(parts[-2:]) if len(parts) > 2 else name
        return name

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
        import json
        from karate_graph_analyzer.visualization.templates import (
            LAYOUT_TEMPLATE,
            GRAPH_STYLE,
            GRAPH_JS_SCRIPT
        )

        # 1. Prepare Node Meta-Data for JS
        js_data = {}
        for node_id, node in self.graph.nodes.items():
            js_data[node_id] = {
                "id": node_id,
                "name": node.name,
                "type": node.type.value,
                "execution_status": node.execution_status,
                "execution_details": node.execution_details,
                "execution_history": getattr(node.metadata, 'execution_history', []),
                "failure_impact_score": getattr(node, 'failure_impact_score', 0),
                "suggestions": getattr(node, 'suggestions', []),
                "file_path": node.metadata.file_path,
                "jira_tags": node.metadata.jira_tags,
                "tags": node.tags
            }

        # 2. Extract Pyvis data (it writes them into the HTML)
        with open(output_file, 'r', encoding='utf-8') as f:
            raw_content = f.read()

        # Extract nodes and edges JSON from the generated file (it uses DataSet({ ... }))
        import re
        nodes_match = re.search(r'nodes = new vis\.DataSet\((.*?)\);', raw_content, re.DOTALL)
        edges_match = re.search(r'edges = new vis\.DataSet\((.*?)\);', raw_content, re.DOTALL)
        options_match = re.search(r'var options = (\{.*?\});', raw_content, re.DOTALL)
        
        nodes_json = nodes_match.group(1) if nodes_match else "[]"
        edges_json = edges_match.group(1) if edges_match else "[]"
        options_json = options_match.group(1) if options_match else "{}"

        # 3. Get configuration
        jira_url = ""
        if hasattr(self.graph, 'config') and self.graph.config:
            jira_url = self.graph.config.jira_base_url or ""

        # 4. Assemble the final Command Center
        final_html = LAYOUT_TEMPLATE.format(
            style=GRAPH_STYLE,
            script=GRAPH_JS_SCRIPT,
            graph_nodes_json=nodes_json, 
            graph_edges_json=edges_json,
            metadata_json=json.dumps(js_data),
            hotspots_json=json.dumps(getattr(self, 'hotspots', [])),
            mode=self.mode.value,
            jira_url=jira_url,
            options_json=options_json
        )

        # 5. Overwrite the file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_html)

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
