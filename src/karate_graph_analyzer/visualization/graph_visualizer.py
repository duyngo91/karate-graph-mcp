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
                    "navigationButtons": false,
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
        
        # Prepare node data for JavaScript
        import json
        js_node_data = {}
        for node_id, node in self.graph.nodes.items():
            js_node_data[node_id] = {
                "name": node.name,
                "type": node.type.value,
                "file_path": node.metadata.file_path,
                "line_number": node.metadata.line_number,
                "jira_tags": node.metadata.jira_tags,
                "additional_data": node.metadata.additional_data
            }
        
        # Insert legend and populate data
        legend_html = getattr(net, 'legend_html', "")
        legend_html = legend_html.replace('DATA_PLACEHOLDER', json.dumps(js_node_data))
        
        html_content = html_content.replace('</body>', f'{legend_html}</body>')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Graph visualization saved to: {output_file.absolute()}")
        return str(output_file.absolute())

    def _add_legend(self, net) -> None:
        """Add collapsible legend and node details sidebar to visualization."""
        legend_html = """
        <style>
            #legend-container {
                position: absolute;
                top: 20px;
                right: 20px;
                z-index: 1000;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            /* Force hide Vis.js navigation buttons */
            .vis-navigation {
                display: none !important;
            }

            #legend {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                max-width: 300px;
                transition: all 0.3s ease;
            }
            #legend.minimized {
                display: none;
            }
            #legend-toggle {
                position: absolute;
                top: 0;
                right: 0;
                background: #333;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                cursor: pointer;
                font-size: 12px;
                z-index: 1001;
            }
            .legend-item {
                margin-bottom: 8px;
                display: flex;
                align-items: center;
                font-size: 13px;
            }
            .legend-color {
                width: 16px;
                height: 16px;
                margin-right: 10px;
                border: 1px solid #666;
                flex-shrink: 0;
            }
            #node-details {
                position: absolute;
                bottom: 20px;
                left: 20px;
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 20px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                width: 350px;
                max-height: 400px;
                overflow-y: auto;
                display: none;
                z-index: 1000;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            .detail-header {
                font-weight: bold;
                font-size: 18px;
                border-bottom: 2px solid #4CAF50;
                margin-bottom: 15px;
                padding-bottom: 5px;
                color: #333;
            }
            .detail-row {
                margin-bottom: 10px;
                font-size: 14px;
                display: flex;
                align-items: flex-start;
            }
            .detail-label {
                font-weight: bold;
                color: #666;
                width: 140px;
                display: inline-block;
                margin-right: 10px;
                flex-shrink: 0;
            }
            .detail-value {
                color: #111;
                word-break: break-word;
                flex: 1;
            }
            .jira-tag {
                display: inline-block;
                background: #E3F2FD;
                color: #1976D2;
                padding: 2px 6px;
                border-radius: 4px;
                margin-right: 5px;
                font-size: 12px;
                font-weight: bold;
            }
        </style>

        <div id="legend-container">
            <button id="legend-toggle" onclick="toggleLegend()">Legend ☰</button>
            <div id="legend">
                <h3 style="margin: 0 0 12px 0; font-size: 16px;">📊 Graph Legend</h3>
                <div class="legend-item"><span class="legend-color" style="background: #4CAF50;"></span><strong>Test Case</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #2196F3; border-radius: 50%;"></span><strong>Workflow</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #9C27B0; transform: rotate(45deg);"></span><strong>Scenario (@tag)</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #FF9800; transform: rotate(45deg);"></span><strong>API Method</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #FF5722; clip-path: polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%);"></span><strong>Domain (Root)</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #FFB74D; border-radius: 50%;"></span><strong>API Path</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #9C27B0; clip-path: polygon(50% 0%, 0% 100%, 100% 100%);"></span><strong>Page Object</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #E91E63; transform: rotate(45deg);"></span><strong>Action (@tag)</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #F44336;"></span><strong>Database</strong></div>
                <hr>
                <div style="font-size: 11px; color: #777;">Click a node to see details</div>
            </div>
        </div>

        <div id="node-details">
            <div id="details-content">
                <div class="detail-header">Node Details</div>
                <p>Select a node to see full information.</p>
            </div>
        </div>

        <script>
            function toggleLegend() {
                var legend = document.getElementById('legend');
                if (legend.style.display === 'none') {
                    legend.style.display = 'block';
                } else {
                    legend.style.display = 'none';
                }
            }

            // This data will be populated by Python
            var nodeData = DATA_PLACEHOLDER;
            var isFocused = false;

            // Handle double click to focus on a node and its full recursive dependency chain
            network.on("doubleClick", function(params) {
                if (params.nodes.length > 0) {
                    var targetId = params.nodes[0];
                    var nodesToKeep = new Set();
                    nodesToKeep.add(targetId);

                    // Recursive function to find all descendants
                    function findDescendants(nodeId) {
                        var children = network.getConnectedNodes(nodeId, 'to');
                        children.forEach(function(childId) {
                            if (!nodesToKeep.has(childId)) {
                                nodesToKeep.add(childId);
                                findDescendants(childId);
                            }
                        });
                    }

                    // Recursive function to find all ancestors
                    function findAncestors(nodeId) {
                        var parents = network.getConnectedNodes(nodeId, 'from');
                        parents.forEach(function(parentId) {
                            if (!nodesToKeep.has(parentId)) {
                                nodesToKeep.add(parentId);
                                findAncestors(parentId);
                            }
                        });
                    }

                    // Find everything
                    findDescendants(targetId);
                    findAncestors(targetId);

                    // Add immediate neighbors of every node in the chain to show context
                    // (e.g., other nodes pointing to the same children)
                    var contextNodes = new Set();
                    nodesToKeep.forEach(function(nodeId) {
                        var neighbors = network.getConnectedNodes(nodeId);
                        neighbors.forEach(function(neighborId) {
                            contextNodes.add(neighborId);
                        });
                    });
                    
                    // Merge context into nodesToKeep
                    contextNodes.forEach(id => nodesToKeep.add(id));

                    // Update all nodes visibility
                    var allNodeIds = nodes.getIds();
                    var updates = allNodeIds.map(function(id) {
                        return { id: id, hidden: !nodesToKeep.has(id) };
                    });
                    nodes.update(updates);
                    isFocused = true;
                    
                    // Fit view to focused nodes
                    setTimeout(function() {
                        network.fit({
                            nodes: Array.from(nodesToKeep),
                            animation: true
                        });
                    }, 100);
                }
            });

            // Handle single click to show details or reset focus
            network.on("click", function(params) {
                var detailsDiv = document.getElementById('node-details');
                
                // If clicked on background, reset focus
                if (params.nodes.length === 0) {
                    if (isFocused) {
                        var allNodeIds = nodes.getIds();
                        var updates = allNodeIds.map(function(id) {
                            return { id: id, hidden: false };
                        });
                        nodes.update(updates);
                        isFocused = false;
                        network.fit({ animation: true });
                    }
                    detailsDiv.style.display = 'none';
                    return;
                }

                // Show details for single clicked node
                var nodeId = params.nodes[0];
                var data = nodeData[nodeId];
                if (data) {
                    var html = '<div class="detail-header">' + data.name + '</div>';
                    html += '<div class="detail-row"><span class="detail-label">Type:</span><span class="detail-value">' + data.type + '</span></div>';
                    
                    if (data.file_path) {
                        html += '<div class="detail-row"><span class="detail-label">File:</span><span class="detail-value">' + data.file_path + '</span></div>';
                    }
                    if (data.line_number) {
                        html += '<div class="detail-row"><span class="detail-label">Line:</span><span class="detail-value">' + data.line_number + '</span></div>';
                    }
                    
                    if (data.jira_tags && data.jira_tags.length > 0) {
                        html += '<div class="detail-row"><span class="detail-label">Jira:</span>';
                        data.jira_tags.forEach(function(tag) {
                            html += '<span class="jira-tag">' + tag + '</span>';
                        });
                        html += '</div>';
                    }

                    if (data.additional_data) {
                        html += '<hr><div style="font-weight:bold; margin-bottom:5px;">Metadata:</div>';
                        for (var key in data.additional_data) {
                            var val = data.additional_data[key];
                            if (val && typeof val !== 'object') {
                                html += '<div class="detail-row" style="font-size:12px;"><span class="detail-label">' + key + ':</span><span class="detail-value">' + val + '</span></div>';
                            }
                        }
                    }

                    document.getElementById('details-content').innerHTML = html;
                    detailsDiv.style.display = 'block';
                }
            });
        </script>
        """
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
