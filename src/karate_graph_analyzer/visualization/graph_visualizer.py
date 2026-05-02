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
from karate_graph_analyzer.visualization.templates import (
    FULL_LEGEND_TEMPLATE
)

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

    # Status colors for Execution/Diff modes
    STATUS_COLORS = {
        "PASSED": "#4CAF50",
        "FAILED": "#F44336",
        "ADDED": "#4CAF50",
        "REMOVED": "#F44336",
        "MODIFIED": "#FF9800",
        "NEUTRAL": "#9E9E9E", # Gray for unchanged
    }

    NODE_SHAPES = {
        NodeType.TEST_CASE: "dot",
        NodeType.WORKFLOW: "dot",
        NodeType.COMMON: "dot",
        NodeType.SCENARIO: "diamond",
        NodeType.API: "diamond",
        NodeType.API_GROUP: "hexagon",
        NodeType.PAGE: "triangle",
        NodeType.ACTION: "diamond",
        NodeType.DATABASE: "square",
        NodeType.LOCATOR: "dot",
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
        self._add_graph_elements(net)
        self._add_legend(net)

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
            "navigationButtons": physics_enabled,
            "keyboard": {"enabled": True, "bindToWindow": False}
        }
        net.set_options(json.dumps(options))

    def _add_graph_elements(self, net: Any):
        """Add nodes and edges from the dependency graph using mode-specific coloring."""
        # 1. Add Nodes
        for node in self.graph.nodes.values():
            level = node.metadata.additional_data.get("level", 0)
            is_root_domain = (node.type == NodeType.API_GROUP and level == 0)
            is_api_path = (node.type == NodeType.API_GROUP and level > 0)
            
            mass = 5 if is_root_domain else 1
            
            # Initialize with default type-based styles
            color = self.NODE_COLORS.get(node.type, "#808080")
            shape = self.NODE_SHAPES.get(node.type, "dot")
            size = 25
            
            # Sub-type styling for API Groups
            if is_root_domain:
                color = "#FF5722" # Deep Orange
                shape = "hexagon"
                size = 40
            elif is_api_path:
                color = "#FFB74D" # Lighter Orange
                shape = "dot"
                size = 25

            border_width = 1
            border_color = "#2c3e50"
            node_name = node.name
            
            # OVERRIDE based on mode and status
            if self.mode == VisualizationMode.EXECUTION:
                if node.execution_status == "PASSED":
                    color = self.STATUS_COLORS["PASSED"]
                    border_width = 3
                    border_color = color
                elif node.execution_status == "FAILED":
                    color = self.STATUS_COLORS["FAILED"]
                    border_width = 3
                    border_color = color
                else:
                    color = self.STATUS_COLORS["NEUTRAL"]
                    border_width = 1
            
            elif self.mode == VisualizationMode.DIFF:
                if node.diff_status == DiffStatus.ADDED:
                    color = self.STATUS_COLORS["ADDED"]
                    border_width = 3
                    border_color = color
                elif node.diff_status == DiffStatus.REMOVED:
                    color = self.STATUS_COLORS["REMOVED"]
                    border_width = 3
                    border_color = color
                    node_name = f"[REMOVED] {node.name}"
                elif node.diff_status == DiffStatus.MODIFIED:
                    color = self.STATUS_COLORS["MODIFIED"]
                    border_width = 3
                    border_color = color
                else:
                    color = self.STATUS_COLORS["NEUTRAL"]
                    border_width = 1
            
            net.add_node(
                node.id,
                label=self._get_display_label(node_name),
                title=self._build_tooltip(node),
                color={"background": color, "border": border_color},
                borderWidth=border_width,
                shape=shape,
                size=size,
                mass=mass
            )

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
        parts = [f"<b>{node.name}</b>", f"<b>Type:</b> {node.type.value}", f"ID: {node.id}"]
        if node.metadata.file_path: parts.append(f"<b>File:</b> {node.metadata.file_path}")
        
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
        return "<br>".join(parts)

    def _post_process_html(self, output_file: Path):
        """Inject custom data and title into generated HTML."""
        with open(output_file, 'r', encoding='utf-8') as f:
            content = f.read()

        js_data = {}
        for node_id, node in self.graph.nodes.items():
            js_data[node_id] = {
                "name": node.name, "type": node.type.value,
                "file_path": node.metadata.file_path, "line_number": node.metadata.line_number,
                "jira_tags": node.metadata.jira_tags,
                "tags": [t for t in node.tags if not (t.startswith("@ALM2:") or t == "@ignore")],
                "execution_status": node.execution_status,
                "execution_details": node.execution_details,
                "diff_status": node.diff_status.value if hasattr(node.diff_status, 'value') else node.diff_status,
                "visualization_mode": self.mode.value if hasattr(self.mode, 'value') else self.mode,
                "additional_data": {k: v for k, v in node.metadata.additional_data.items() if k != "tags"}
            }

        title = f"<h1 style='text-align: center; font-family: Inter; margin-top: 20px; color: #333;'>Karate Graph: {self.graph.project_name}</h1>"
        content = content.replace('<h1></h1>', title, 1).replace('<h1></h1>', '')
        
        final_legend = FULL_LEGEND_TEMPLATE.replace('DATA_PLACEHOLDER', json.dumps(js_data))
        content = content.replace('</body>', f'{final_legend}</body>')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)

    def _add_legend(self, net: Any):
        net.legend_html = FULL_LEGEND_TEMPLATE

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
