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
        NodeType.COMMON: "#2196F3",         # Blue (shared with workflow family)
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
        NodeType.COMMON: "ellipse",
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
                        "gravitationalConstant": -150,
                        "centralGravity": 0.005,
                        "springLength": 250,
                        "springConstant": 0.05,
                        "avoidOverlap": 0.2
                    },
                    "maxVelocity": 45,
                    "solver": "forceAtlas2Based",
                    "timestep": 0.35,
                    "stabilization": {
                        "enabled": true,
                        "iterations": 200,
                        "updateInterval": 25
                    }
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
                f"<b>Type:</b> {node.type.value}",
                f"ID: {node.id}"
            ]

            if is_domain:
                title_parts.append("🌐 DOMAIN (Root)")

            if node.metadata.file_path:
                title_parts.append(f"<b>File:</b> {node.metadata.file_path}")

            if node.metadata.line_number:
                title_parts.append(f"<b>Line:</b> {node.metadata.line_number}")

            if node.metadata.jira_tags:
                title_parts.append(f"<b>Jira:</b> {', '.join(node.metadata.jira_tags)}")

            # Filter out @ALM2 and @ignore tags from the tags list
            clean_tags = [t for t in node.tags if not (t.startswith("@ALM2:") or t == "@ignore")]
            
            if clean_tags:
                title_parts.append(f"<b>Tags:</b> {', '.join(clean_tags)}")

            title = "<br>".join(title_parts)

            # Truncate long labels (especially file paths) for better readability
            display_label = node.name
            if len(display_label) > 30 and ("/" in display_label or "\\" in display_label):
                # If it's a path, show only the last two segments
                parts = display_label.replace("\\", "/").split("/")
                if len(parts) > 2:
                    display_label = ".../" + "/".join(parts[-2:])
                elif len(parts) > 1:
                    display_label = "/".join(parts[-2:])

            # Add node with physics properties
            net.add_node(
                node.id,
                label=display_label,
                title=title,
                color=color,
                shape=shape,
                size=size,
                mass=mass,
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
            clean_tags = [t for t in node.tags if not (t.startswith("@ALM2:") or t == "@ignore")]
            
            # Clean additional_data
            clean_additional = {k: v for k, v in node.metadata.additional_data.items() if k != "tags"}
            if "scenario_tags" in clean_additional and isinstance(clean_additional["scenario_tags"], list):
                clean_additional["scenario_tags"] = [t for t in clean_additional["scenario_tags"] if not (t.startswith("@ALM2:") or t == "@ignore")]
                
            js_node_data[node_id] = {
                "name": node.name,
                "type": node.type.value,
                "file_path": node.metadata.file_path,
                "line_number": node.metadata.line_number,
                "jira_tags": node.metadata.jira_tags,
                "tags": clean_tags,
                "additional_data": clean_additional
            }
        
        # Replace empty h1 tags with a proper title
        title_html = f"<h1 style='text-align: center; font-family: Segoe UI, Tahoma; margin-top: 20px; color: #333;'>Karate Dependency Graph: {self.graph.project_name}</h1>"
        html_content = html_content.replace('<h1></h1>', title_html, 1) # Replace first one
        html_content = html_content.replace('<h1></h1>', '', 1) # Remove second one
        
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
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

            body {
                background-color: #f8f9fa;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
            }

            #legend-container {
                position: absolute;
                top: 20px;
                right: 20px;
                z-index: 1000;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }

            .glass-panel {
                background: rgba(255, 255, 255, 0.85);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                padding: 15px;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }

            #search-container {
                width: 300px;
            }

            .search-input-wrapper {
                position: relative;
                display: flex;
                align-items: center;
            }

            #node-search {
                width: 100%;
                padding: 10px 15px;
                padding-right: 35px;
                border-radius: 8px;
                border: 1px solid #ddd;
                font-size: 14px;
                outline: none;
                transition: border-color 0.2s;
            }

            #node-search:focus {
                border-color: #2196F3;
                box-shadow: 0 0 0 2px rgba(33, 150, 243, 0.1);
            }

            .search-icon {
                position: absolute;
                right: 10px;
                color: #888;
                pointer-events: none;
            }

            #search-results {
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                background: white;
                border-radius: 0 0 8px 8px;
                border: 1px solid #ddd;
                border-top: none;
                max-height: 200px;
                overflow-y: auto;
                display: none;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                margin-top: -1px;
            }

            .search-result-item {
                padding: 8px 15px;
                cursor: pointer;
                font-size: 13px;
                border-bottom: 1px solid #f0f0f0;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            .search-result-item:hover {
                background-color: #f5f5f5;
            }

            .search-result-type {
                font-size: 10px;
                text-transform: uppercase;
                background: #eee;
                padding: 2px 5px;
                border-radius: 4px;
                color: #666;
            }

            #legend {
                width: 300px;
            }

            #legend-toggle {
                align-self: flex-end;
                background: #333;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 15px;
                cursor: pointer;
                font-size: 12px;
                font-weight: 600;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }

            .legend-item {
                margin-bottom: 10px;
                display: flex;
                align-items: center;
                font-size: 13px;
                font-weight: 500;
                color: #444;
            }

            .legend-color {
                width: 14px;
                height: 14px;
                margin-right: 12px;
                border: 1.5px solid rgba(0,0,0,0.1);
                flex-shrink: 0;
            }

            #node-details {
                position: absolute;
                bottom: 25px;
                left: 25px;
                background: rgba(255, 255, 255, 0.9);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 12px;
                padding: 25px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                width: 380px;
                max-height: 450px;
                overflow-y: auto;
                display: none;
                z-index: 1000;
            }

            .detail-header {
                font-weight: 700;
                font-size: 20px;
                border-bottom: 3px solid #2196F3;
                margin-bottom: 18px;
                padding-bottom: 8px;
                color: #1a1a1a;
            }

            .detail-row {
                margin-bottom: 12px;
                font-size: 14px;
                line-height: 1.4;
            }

            .detail-label {
                font-weight: 600;
                color: #777;
                width: 120px;
                display: inline-block;
            }

            .detail-value {
                color: #222;
                word-break: break-all;
            }
        </style>

        <div id="legend-container">
            <div id="search-container" class="glass-panel">
                <div class="search-input-wrapper">
                    <input type="text" id="node-search" placeholder="Search nodes (Ctrl+K)..." oninput="handleSearch(this.value)">
                    <span class="search-icon">🔍</span>
                </div>
                <div id="search-results"></div>
            </div>

            <button id="legend-toggle" onclick="toggleLegend()">Legend ☰</button>
            <div id="legend" class="glass-panel">
                <h3 style="margin: 0 0 15px 0; font-size: 16px; color: #111;">📊 Graph Components</h3>
                <div class="legend-item"><span class="legend-color" style="background: #4CAF50; border-radius: 4px;"></span><strong>Test Case</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #2196F3; border-radius: 50%;"></span><strong>Workflow / Common</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #9C27B0; transform: rotate(45deg);"></span><strong>Scenario (@tag)</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #FF9800; transform: rotate(45deg);"></span><strong>API Method</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #FF5722; clip-path: polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%);"></span><strong>Domain (Root)</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #FFB74D; border-radius: 50%;"></span><strong>API Path</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #9C27B0; clip-path: polygon(50% 0%, 0% 100%, 100% 100%);"></span><strong>Page Object</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #E91E63; transform: rotate(45deg);"></span><strong>Action (@tag)</strong></div>
                <div class="legend-item"><span class="legend-color" style="background: #F44336; border-radius: 4px;"></span><strong>Database</strong></div>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 15px 0;">
                <div style="font-size: 11px; color: #888; line-height: 1.5;">
                    💡 <b>Double-click</b> to focus chain<br>
                    💡 <b>Click</b> background to reset<br>
                    💡 <b>Scroll</b> to zoom
                </div>
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

            var nodeData = DATA_PLACEHOLDER;
            var isFocused = false;

            // Search functionality
            function handleSearch(query) {
                const resultsDiv = document.getElementById('search-results');
                if (!query || query.length < 2) {
                    resultsDiv.style.display = 'none';
                    return;
                }

                const searchTerms = query.toLowerCase().split(' ');
                const matches = [];
                
                for (const id in nodeData) {
                    const node = nodeData[id];
                    const searchableText = (node.name + ' ' + node.type + ' ' + (node.file_path || '')).toLowerCase();
                    
                    if (searchTerms.every(term => searchableText.includes(term))) {
                        matches.push({ id, ...node });
                    }
                    if (matches.length >= 10) break;
                }

                if (matches.length > 0) {
                    resultsDiv.innerHTML = matches.map(m => `
                        <div class="search-result-item" onclick="focusOnNode('${m.id}')">
                            <span>${m.name.length > 35 ? '...' + m.name.slice(-32) : m.name}</span>
                            <span class="search-result-type">${m.type}</span>
                        </div>
                    `).join('');
                    resultsDiv.style.display = 'block';
                } else {
                    resultsDiv.style.display = 'none';
                }
            }

            function focusOnNode(nodeId) {
                document.getElementById('search-results').style.display = 'none';
                document.getElementById('node-search').value = nodeData[nodeId].name;
                
                // Show all nodes first if we were focused
                if (isFocused) {
                    resetFocus();
                }

                network.focus(nodeId, {
                    scale: 1.2,
                    animation: {
                        duration: 1000,
                        easingFunction: 'easeInOutQuad'
                    }
                });
                
                // Trigger click to show details
                network.selectNodes([nodeId]);
                showDetails(nodeId);
            }

            function resetFocus() {
                var allNodeIds = nodes.getIds();
                var updates = allNodeIds.map(function(id) {
                    return { id: id, hidden: false };
                });
                nodes.update(updates);
                isFocused = false;
                network.fit({ animation: true });
            }

            // Keyboard shortcut Ctrl+K to search
            document.addEventListener('keydown', function(e) {
                if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                    e.preventDefault();
                    document.getElementById('node-search').focus();
                }
            });

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
                        resetFocus();
                    }
                    detailsDiv.style.display = 'none';
                    document.getElementById('search-results').style.display = 'none';
                    return;
                }

                // Show details for single clicked node
                showDetails(params.nodes[0]);
            });

            function showDetails(nodeId) {
                var detailsDiv = document.getElementById('node-details');
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
            }

            // Safe initialization for custom events
            function initEvents() {
                if (typeof network !== 'undefined') {
                    // Disable physics after initial stabilization to keep UI responsive
                    network.on("stabilizationIterationsDone", function() {
                        console.log("Karate Graph: Stabilization complete, disabling physics for performance.");
                        network.setOptions({ physics: { enabled: false } });
                    });

                    // Handle double click to focus on a node and its full recursive dependency chain
                    network.on("doubleClick", function(params) {
                        if (params.nodes.length > 0) {
                            // Disable physics during focus to prevent lag
                            network.setOptions({ physics: { enabled: false } });
                            
                            var targetId = params.nodes[0];
                            var nodesToKeep = new Set();
                            nodesToKeep.add(targetId);

                            function findDescendants(nodeId) {
                                var children = network.getConnectedNodes(nodeId, 'to');
                                children.forEach(function(childId) {
                                    if (!nodesToKeep.has(childId)) {
                                        nodesToKeep.add(childId);
                                        findDescendants(childId);
                                    }
                                });
                            }

                            function findAncestors(nodeId) {
                                var parents = network.getConnectedNodes(nodeId, 'from');
                                parents.forEach(function(parentId) {
                                    if (!nodesToKeep.has(parentId)) {
                                        nodesToKeep.add(parentId);
                                        findAncestors(parentId);
                                    }
                                });
                            }

                            findDescendants(targetId);
                            findAncestors(targetId);

                            var contextNodes = new Set();
                            nodesToKeep.forEach(function(nodeId) {
                                var neighbors = network.getConnectedNodes(nodeId);
                                neighbors.forEach(function(neighborId) {
                                    contextNodes.add(neighborId);
                                });
                            });
                            
                            contextNodes.forEach(id => nodesToKeep.add(id));

                            var allNodeIds = nodes.getIds();
                            var updates = allNodeIds.map(function(id) {
                                return { id: id, hidden: !nodesToKeep.has(id) };
                            });
                            nodes.update(updates);
                            isFocused = true;
                            
                            setTimeout(function() {
                                network.fit({
                                    nodes: Array.from(nodesToKeep),
                                    animation: {
                                        duration: 800,
                                        easingFunction: 'easeInOutQuad'
                                    }
                                });
                            }, 50);
                        }
                    });

                    // Handle single click to show details or reset focus
                    network.on("click", function(params) {
                        var detailsDiv = document.getElementById('node-details');
                        if (params.nodes.length === 0) {
                            if (isFocused) {
                                resetFocus();
                            }
                            detailsDiv.style.display = 'none';
                            document.getElementById('search-results').style.display = 'none';
                            return;
                        }
                        showDetails(params.nodes[0]);
                    });

                    console.log("Karate Graph: Custom events initialized successfully.");
                } else {
                    setTimeout(initEvents, 100);
                }
            }

            function resetFocus() {
                var allNodeIds = nodes.getIds();
                var updates = allNodeIds.map(function(id) {
                    return { id: id, hidden: false };
                });
                nodes.update(updates);
                isFocused = false;
                
                // Don't re-enable physics automatically as it might cause jumps
                // Just fit the view
                network.fit({ animation: true });
            }

            initEvents();
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
