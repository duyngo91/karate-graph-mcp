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

LEGEND_HTML_BODY = """
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
        
        <h3 style="margin: 15px 0 10px 0; font-size: 14px; color: #111;">🚥 Execution</h3>
        <div class="legend-item"><span class="legend-color" style="background: #4CAF50; border-radius: 50%;"></span><strong>Passed</strong></div>
        <div class="legend-item"><span class="legend-color" style="background: #F44336; border-radius: 50%;"></span><strong>Failed</strong></div>

        <h3 style="margin: 15px 0 10px 0; font-size: 14px; color: #111;">⚖️ Comparison (Diff)</h3>
        <div class="legend-item"><span class="legend-color" style="background: #4CAF50; border-radius: 4px;"></span><strong>Added</strong></div>
        <div class="legend-item"><span class="legend-color" style="background: #F44336; border-radius: 4px;"></span><strong>Removed</strong></div>
        <div class="legend-item"><span class="legend-color" style="background: #FF9800; border-radius: 4px;"></span><strong>Modified</strong></div>
        <div class="legend-item"><span class="legend-color" style="background: #9E9E9E; border-radius: 4px;"></span><strong>Unchanged</strong></div>

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
"""

FULL_LEGEND_TEMPLATE = f"""
<style>
{GRAPH_STYLE}
</style>

{LEGEND_HTML_BODY}

<script>
{GRAPH_JS_SCRIPT}
</script>
"""
