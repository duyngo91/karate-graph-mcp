"""
Graph visualization module.

Provides interactive HTML visualization of dependency graphs.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from karate_graph_analyzer.models import DependencyGraph, NodeType

logger = logging.getLogger(__name__)


class GraphVisualizer:
    """Interactive graph visualizer using pyvis."""

    # Color scheme for different node types
    NODE_COLORS = {
        NodeType.TEST_CASE: "#4CAF50",      # Green
        NodeType.WORKFLOW: "#2196F3",       # Blue
        NodeType.API: "#FF9800",            # Orange
        NodeType.API_GROUP: "#FFB74D",      # Light Orange (for API hierarchy)
        NodeType.PAGE: "#9C27B0",           # Purple
        NodeType.DATABASE: "#F44336",       # Red
        NodeType.SCENARIO: "#9C27B0",       # Purple (same as workflow family)
        NodeType.ACTION: "#E91E63",         # Pink (page action family)
        NodeType.LOCATOR: "#607D8B",        # Blue Grey
    }

    # Shape scheme for different node types
    NODE_SHAPES = {
        NodeType.TEST_CASE: "box",
        NodeType.WORKFLOW: "ellipse",
        NodeType.API: "diamond",
        NodeType.API_GROUP: "dot",          # Circle for API groups
        NodeType.PAGE: "triangle",
        NodeType.DATABASE: "database",
        NodeType.SCENARIO: "diamond",       # Diamond for scenarios
        NodeType.ACTION: "diamond",         # Diamond for actions
        NodeType.LOCATOR: "hexagon",        # Hexagon for locators
    }

    def __init__(self, graph: DependencyGraph):
        """Initialize visualizer with dependency graph.

        Args:
            graph: Dependency graph to visualize
        """
        self.graph = graph
        logger.info(f"Initialized GraphVisualizer for project '{graph.project_name}'")

    def render(
        self,
        output_path: str = "graph.html",
        height: str = "750px",
        width: str = "100%",
        notebook: bool = False,
        directed: bool = True,
        physics_enabled: bool = True,
    ) -> str:
        """Render graph to interactive HTML.

        Args:
            output_path: Path to save HTML file
            height: Height of visualization
            width: Width of visualization
            notebook: Whether rendering in Jupyter notebook
            directed: Whether to show directed edges
            physics_enabled: Whether to enable physics simulation

        Returns:
            Path to generated HTML file
        """
        try:
            from pyvis.network import Network
        except ImportError:
            logger.error("pyvis not installed. Install with: pip install pyvis")
            raise ImportError(
                "pyvis is required for visualization. "
                "Install with: pip install pyvis"
            )

        logger.info(f"Rendering graph with {len(self.graph.nodes)} nodes")

        # Create network
        net = Network(
            height=height,
            width=width,
            notebook=notebook,
            directed=directed,
        )

        # Configure physics and interaction
        if physics_enabled:
            net.set_options("""
            {
                "physics": {
                    "enabled": true,
                    "forceAtlas2Based": {
                        "gravitationalConstant": -50,
                        "centralGravity": 0.01,
                        "springLength": 200,
                        "springConstant": 0.08
                    },
                    "maxVelocity": 50,
                    "solver": "forceAtlas2Based",
                    "timestep": 0.35,
                    "stabilization": {"iterations": 150}
                },
                "interaction": {
                    "dragNodes": true,
                    "dragView": true,
                    "zoomView": true,
                    "hover": true,
                    "navigationButtons": true,
                    "keyboard": {
                        "enabled": true,
                        "bindToWindow": false
                    }
                }
            }
            """)
        else:
            net.set_options("""
            {
                "physics": {
                    "enabled": false
                },
                "interaction": {
                    "dragNodes": true,
                    "dragView": true,
                    "zoomView": true,
                    "hover": true,
                    "navigationButtons": true,
                    "keyboard": {
                        "enabled": true,
                        "bindToWindow": false
                    }
                }
            }
            """)

        # Add nodes
        for node in self.graph.nodes.values():
            color = self.NODE_COLORS.get(node.type, "#808080")
            shape = self.NODE_SHAPES.get(node.type, "dot")
            size = 25
            mass = 1  # Default mass

            # Special handling for domain nodes (API_GROUP at level 0)
            is_domain = False
            if node.type == NodeType.API_GROUP:
                level = node.metadata.additional_data.get("level", -1)
                if level == 0:
                    # Domain node - make it stand out and act as anchor
                    is_domain = True
                    shape = "hexagon"
                    size = 40  # Larger size
                    color = "#FF5722"  # Deep Orange for domains
                    mass = 5  # Much heavier to act as gravity center

            # Build title (tooltip) with metadata
            title_parts = [
                f"<b>{node.name}</b>",
                f"Type: {node.type.value}",
                f"ID: {node.id}",
            ]

            if is_domain:
                title_parts.append("🌐 DOMAIN (Root)")

            if node.metadata.file_path:
                title_parts.append(f"File: {node.metadata.file_path}")

            if node.metadata.line_number:
                title_parts.append(f"Line: {node.metadata.line_number}")

            if node.metadata.jira_tags:
                title_parts.append(f"Jira: {', '.join(node.metadata.jira_tags)}")

            title = "<br>".join(title_parts)

            # Add node with physics properties
            net.add_node(
                node.id,
                label=node.name,
                title=title,
                color=color,
                shape=shape,
                size=size,
                mass=mass,  # Heavier nodes act as gravity centers
            )

        # Add edges
        for edge in self.graph.edges.values():
            # Edge color based on dependency type
            edge_colors = {
                "WORKFLOW": "#2196F3",
                "API": "#FF9800",
                "PAGE": "#9C27B0",
                "DATABASE": "#F44336",
            }
            edge_color = edge_colors.get(edge.type.value, "#808080")

            net.add_edge(
                edge.from_node,
                edge.to_node,
                title=f"Type: {edge.type.value}",
                color=edge_color,
                arrows="to",
            )

        # Highlight cycles if any
        if self.graph.cycles:
            logger.info(f"Highlighting {len(self.graph.cycles)} cycles")
            for cycle in self.graph.cycles:
                for i in range(len(cycle)):
                    from_node = cycle[i]
                    to_node = cycle[(i + 1) % len(cycle)]

                    # Find and update edge to highlight cycle
                    for edge in net.edges:
                        if edge["from"] == from_node and edge["to"] == to_node:
                            edge["color"] = "#FF0000"  # Red for cycles
                            edge["width"] = 3
                            edge["title"] = "⚠️ CYCLE DETECTED"

        # Add legend
        self._add_legend(net)

        # Save to file
        output_file = Path(output_path)
        net.save_graph(str(output_file))
        
        # Inject custom controls and legend HTML into the generated file
        with open(output_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Insert legend before closing body tag
        legend_html = ""
        if hasattr(net, 'legend_html'):
            legend_html = net.legend_html
        
        html_content = html_content.replace('</body>', f'{legend_html}</body>')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Graph visualization saved to: {output_file.absolute()}")
        return str(output_file.absolute())

    def _add_legend(self, net) -> None:
        """Add legend to visualization.

        Args:
            net: Pyvis network object
        """
        # Add legend as HTML overlay
        legend_html = """
        <div id="legend" style="
            position: absolute;
            top: 20px;
            right: 20px;
            background: white;
            border: 2px solid #333;
            border-radius: 8px;
            padding: 15px;
            font-family: Arial, sans-serif;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            z-index: 1000;
            max-width: 300px;
        ">
            <h3 style="margin: 0 0 10px 0; font-size: 16px; border-bottom: 2px solid #333; padding-bottom: 5px;">
                📊 Legend
            </h3>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #4CAF50; border: 1px solid #333; margin-right: 8px; vertical-align: middle;"></span>
                <strong>Test Case</strong> - Scenario hoặc test
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #2196F3; border: 1px solid #333; border-radius: 50%; margin-right: 8px; vertical-align: middle;"></span>
                <strong>Workflow</strong> - Reusable workflow
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #9C27B0; border: 1px solid #333; transform: rotate(45deg); margin-right: 8px; vertical-align: middle;"></span>
                <strong>Scenario</strong> - Workflow scenario (@tag)
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #FF9800; border: 1px solid #333; transform: rotate(45deg); margin-right: 8px; vertical-align: middle;"></span>
                <strong>API Method</strong> - HTTP method (GET, POST, etc.)
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #FF5722; border: 1px solid #333; margin-right: 8px; vertical-align: middle;">⬡</span>
                <strong>Domain</strong> - API domain (root)
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #FFB74D; border: 1px solid #333; border-radius: 50%; margin-right: 8px; vertical-align: middle;"></span>
                <strong>API Path</strong> - API path segment
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 0; height: 0; border-left: 10px solid transparent; border-right: 10px solid transparent; border-bottom: 20px solid #9C27B0; margin-right: 8px; vertical-align: middle;"></span>
                <strong>Page</strong> - Page object
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #E91E63; border: 1px solid #333; transform: rotate(45deg); margin-right: 8px; vertical-align: middle;"></span>
                <strong>Action</strong> - Page action (@tag)
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #F44336; border: 1px solid #333; margin-right: 8px; vertical-align: middle;"></span>
                <strong>Database</strong> - Database operation
            </div>
            <div style="margin-bottom: 8px;">
                <span style="display: inline-block; width: 20px; height: 20px; background: #00BCD4; border: 1px solid #333; margin-right: 8px; vertical-align: middle;">⭐</span>
                <strong>Feature Group</strong> - Feature category
            </div>
            <hr style="margin: 10px 0; border: none; border-top: 1px solid #ccc;">
            <div style="font-size: 12px; color: #666;">
                <strong>💡 Cách sử dụng:</strong><br>
                🖱️ <strong>Click vào node</strong> để focus (chỉ hiện các cấp con)<br>
                🖱️ <strong>Click vào vùng trống</strong> để clear focus<br>
                 Hover để xem chi tiết<br>
                📜 Scroll để zoom in/out<br>
                🌳 Hierarchy: Domain → Path → Method → Test Case → Feature
            </div>
        </div>
        """
        
        # This will be injected into the HTML after generation
        # Store it as an attribute for post-processing
        net.legend_html = legend_html

    def get_statistics(self) -> Dict[str, any]:
        """Get graph statistics for display.

        Returns:
            Dictionary with graph statistics
        """
        node_counts = {}
        for node in self.graph.nodes.values():
            node_type = node.type.value
            node_counts[node_type] = node_counts.get(node_type, 0) + 1

        return {
            "total_nodes": len(self.graph.nodes),
            "total_edges": len(self.graph.edges),
            "node_counts": node_counts,
            "cycles_detected": len(self.graph.cycles),
            "project_name": self.graph.project_name,
        }

    def render_subgraph(
        self,
        node_ids: List[str],
        output_path: str = "subgraph.html",
        **kwargs,
    ) -> str:
        """Render a subgraph containing only specified nodes.

        Args:
            node_ids: List of node IDs to include
            output_path: Path to save HTML file
            **kwargs: Additional arguments for render()

        Returns:
            Path to generated HTML file
        """
        # Create temporary graph with only specified nodes
        from karate_graph_analyzer.models import DependencyGraph

        filtered_nodes = {
            nid: node for nid, node in self.graph.nodes.items() if nid in node_ids
        }

        filtered_edges = {
            eid: edge
            for eid, edge in self.graph.edges.items()
            if edge.from_node in node_ids and edge.to_node in node_ids
        }

        subgraph = DependencyGraph(
            project_name=f"{self.graph.project_name}_subgraph",
            nodes=filtered_nodes,
            edges=filtered_edges,
            cycles=[],
        )

        # Create new visualizer for subgraph
        sub_visualizer = GraphVisualizer(subgraph)
        return sub_visualizer.render(output_path, **kwargs)

    def render_impact_view(
        self,
        changed_component_id: str,
        affected_test_case_ids: List[str],
        output_path: str = "impact_view.html",
        **kwargs,
    ) -> str:
        """Render impact analysis view highlighting affected components.

        Args:
            changed_component_id: ID of changed component
            affected_test_case_ids: IDs of affected test cases
            output_path: Path to save HTML file
            **kwargs: Additional arguments for render()

        Returns:
            Path to generated HTML file
        """
        try:
            from pyvis.network import Network
        except ImportError:
            raise ImportError("pyvis is required for visualization")

        logger.info(
            f"Rendering impact view: {changed_component_id} affects "
            f"{len(affected_test_case_ids)} test cases"
        )

        # Create network
        net = Network(
            height=kwargs.get("height", "750px"),
            width=kwargs.get("width", "100%"),
            directed=True,
        )

        # Add all nodes but highlight affected ones
        for node in self.graph.nodes.values():
            color = self.NODE_COLORS.get(node.type, "#808080")
            shape = self.NODE_SHAPES.get(node.type, "dot")
            size = 25

            # Highlight changed component
            if node.id == changed_component_id:
                color = "#FF0000"  # Red
                size = 40
                border_width = 5

            # Highlight affected test cases
            elif node.id in affected_test_case_ids:
                color = "#FFA500"  # Orange
                size = 30
                border_width = 3
            else:
                border_width = 1

            title_parts = [
                f"<b>{node.name}</b>",
                f"Type: {node.type.value}",
            ]

            if node.id == changed_component_id:
                title_parts.append("⚠️ CHANGED COMPONENT")
            elif node.id in affected_test_case_ids:
                title_parts.append("⚠️ AFFECTED TEST CASE")

            if node.metadata.jira_tags:
                title_parts.append(f"Jira: {', '.join(node.metadata.jira_tags)}")

            title = "<br>".join(title_parts)

            net.add_node(
                node.id,
                label=node.name,
                title=title,
                color=color,
                shape=shape,
                size=size,
                borderWidth=border_width,
            )

        # Add edges
        for edge in self.graph.edges.values():
            net.add_edge(
                edge.from_node,
                edge.to_node,
                title=f"Type: {edge.type.value}",
                arrows="to",
            )

        # Save
        output_file = Path(output_path)
        net.save_graph(str(output_file))

        logger.info(f"Impact view saved to: {output_file.absolute()}")
        return str(output_file.absolute())
