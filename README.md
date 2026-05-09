# Karate Feature Graph Analyzer (MCP-Powered)

A Model Context Protocol (MCP) tool for AI agents to analyze Karate Framework projects, build dependency graphs, and generate interactive reports.

## Why use this with AI?

- Impact analysis with dependency paths and source lines
- Multi-project graph exploration
- Search APIs, workflows, pages, Java/JS usages
- Failure hotspot and flaky-risk prioritization
- Reusable helper discovery before writing new code

## Quick Start

1. Install

```bash
git clone <repository-url>
cd karate-feature-graph-analyzer
pip install -e .
```

2. Configure MCP client

```json
{
  "mcpServers": {
    "karate-analyzer": {
      "command": "python",
      "args": ["-m", "karate_graph_analyzer"],
      "env": {
        "PYTHONPATH": "C:/path/to/repo/src",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

3. Ask your AI to:

- Register and analyze project
- Show impact if a component changes
- Find reusable helpers before creating new ones

## Available AI Tools

- `register_project`
- `analyze_project`
- `bulk_analyze`
- `impact_analysis`
- `search_api`
- `search_workflow`
- `search_test_case`
- `search_java_usage`
- `search_js_usage`
- `search_error_pattern`
- `search_reusable_function`
- `change_impact_preview`
- `test_selection_suggestion`
- `top_hotspots`
- `prioritize_fix_queue`
- `flaky_risk`

## Reuse And Smart Retest

### 1) Reuse search

`search_reusable_function(project_name, query, language, limit)` now returns:

- `tags`
- `aliases`
- `usage_examples`
- `stability_score`

This helps AI pick existing helpers with better confidence.

### 2) Change impact preview

`change_impact_preview(project_name, changed_paths, limit)` maps changed files/components to impacted test cases via dependency paths.

### 3) Test selection suggestion

`test_selection_suggestion(project_name, changed_paths, limit)` suggests a compact high-signal rerun set.

Current strategy:

`priority = trigger_count * 10 - min_depth`

## Visual Reports

Interactive HTML graph output is generated under each project `output/` folder.

## Project Structure

```text
karate-feature-graph-analyzer/
├── src/karate_graph_analyzer/
│   ├── mcp_server.py
│   ├── mcp_interface/
│   ├── parser/
│   ├── graph/
│   └── visualization/
├── output/
└── tests/
```

## License

MIT
