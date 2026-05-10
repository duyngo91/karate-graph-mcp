from pathlib import Path

# Base path for assets
ASSETS_DIR = Path(__file__).parent / "assets"

def get_asset_content(filename):
    """Read content from an asset file."""
    path = ASSETS_DIR / filename
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return f"/* Asset {filename} not found */"

# Dynamic content loading
GRAPH_STYLE = get_asset_content("style.css")
GRAPH_JS_SCRIPT = get_asset_content("script.js")

LAYOUT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Karate Graph Command Center</title>
    <meta charset="utf-8">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        {{STYLE_INJECTION}}
    </style>
</head>
<body>
    <div id="app-container">
        <!-- SIDEBAR -->
        <div id="sidebar">
            <div class="sidebar-header">
                <i class="fas fa-project-diagram"></i> COMMAND CENTER
            </div>
            
            <div class="sidebar-tabs">
                <div class="tab active" onclick="switchTab('hotspots')"><i class="fas fa-fire"></i> Hotspots</div>
                <div class="tab" onclick="switchTab('timeline')"><i class="fas fa-history"></i> History</div>
                <div class="tab" onclick="switchTab('legend')">📖 Legend</div>
            </div>

            <!-- Tab Contents -->
            <div id="hotspots-content" class="tab-content">
                <div id="hotspot-list">
                    <!-- Dynamic hotspots here -->
                </div>
            </div>
            
            <div id="timeline-content" class="tab-content" style="display: none;">
                <div style="padding: 20px; color: #666; font-size: 13px;">
                    <i class="fas fa-info-circle"></i> Select a node to see its detailed execution history.
                </div>
            </div>

            <div id="legend-content" class="tab-content" style="display: none;">
                <!-- Legend rendered via JS -->
            </div>
            
            <div style="padding: 15px; border-top: 1px solid var(--border);">
                <div style="font-size: 11px; font-weight: 800; color: #666; margin-bottom: 10px; text-transform: uppercase;">Layers</div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <label style="display: flex; align-items: center; font-size: 13px; cursor: pointer;">
                        <input type="checkbox" id="toggle-functional" checked onchange="toggleLayer('functional', this.checked)" style="margin-right: 8px;"> 
                        Functional Layer
                    </label>
                    <label style="display: flex; align-items: center; font-size: 13px; cursor: pointer;">
                        <input type="checkbox" id="toggle-structural" checked onchange="toggleLayer('structural', this.checked)" style="margin-right: 8px;"> 
                        Structural Layer
                    </label>
                </div>
            </div>

            <div style="padding: 15px; border-top: 1px solid var(--border);">
                <div style="position: relative;">
                    <input type="text" id="node-search" placeholder="Search test case ID, name, path (Ctrl+K)..."
                           style="width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #ddd; outline: none;"
                           onkeyup="handleSearch(this.value)">
                    <div id="search-results" class="hud-card" style="position: absolute; bottom: 50px; left: 0; right: 0; display: none; max-height: 300px; overflow-y: auto;"></div>
                </div>
            </div>
        </div>

        <!-- MAIN CANVAS AREA -->
        <div id="main-view">
            <!-- TOP HUD (Managerial View) -->
            <div id="top-hud">
                <div id="status-summary" class="hud-card" style="display:none; width: 420px; pointer-events: auto;">
                    <!-- Executive status info -->
                </div>
                
            </div>

            <div id="graph-canvas" style="width: 100%; height: 100%;"></div>

            <!-- LEGEND OVERLAY -->
            <div id="legend-overlay" class="hud-card" style="display:none; width: 280px;">
                <h3 style="margin: 0 0 15px 0; font-size: 14px;">Color Guide</h3>
                <div id="legend-list"></div>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 15px 0;">
                <div style="font-size: 11px; color: #999;">
                    <style>
                    .badge-type { background: #e3f2fd; color: #1976d2; }
                    .badge-utility { background: #607d8b; color: #ffffff; padding: 2px 8px; border-radius: 4px; font-weight: bold; }
                    .badge-passed { background: #e8f5e9; color: #2e7d32; }
                    </style>
                    💡 Double-click to focus chain<br>
                    💡 Click background to reset
                </div>
            </div>
        </div>
    </div>

    <script type="text/javascript">
        // Data injected by Python via string replacement
        var graphNodes = {{GRAPH_NODES}};
        var graphEdges = {{GRAPH_EDGES}};
        var nodeMetadata = {{METADATA}};
        var hotspotData = {{HOTSPOTS}};
        var activeMode = "{{MODE}}";
        var jiraBaseUrl = "{{JIRA_URL}}";
        
        // Initialize Vis.js DataSets
        var nodes = new vis.DataSet(graphNodes);
        var edges = new vis.DataSet(graphEdges);
        
        var container = document.getElementById('graph-canvas');
        var data = { nodes: nodes, edges: edges };
        var options = {{OPTIONS}};
        var network = new vis.Network(container, data, options);
        
        {{SCRIPT_INJECTION}}
    </script>
    {{PROGRESSIVE_MANIFEST_TAG}}
</body>
</html>
"""

# Maintain compatibility with existing calls
FULL_PAGE_TEMPLATE = LAYOUT_TEMPLATE
