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
- `feature_intent_index`
- `variable_data_flow_trace`
- `assertion_map`
- `call_read_deep_context`
- `ai_feature_context_pack`
- `feature_behavior_map`
- `scenario_similarity_map`
- `feature_reuse_advisor`
- `db_query_index`
- `search_db_usage`
- `db_data_flow_trace`
- `db_assertion_map`
- `db_impact_preview`
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

## Feature Understanding For AI

These tools help AI understand Karate `.feature` files before editing or debugging:

- `feature_intent_index(project_name, query, limit)`
  - summarizes scenario intent, step roles, API signals, data files, assertions, and call/read usage
- `variable_data_flow_trace(project_name, feature_path, scenario_tag, scenario_name, node_id, limit)`
  - traces `def`/`set` variables from source expressions to usage lines
- `assertion_map(project_name, query, limit)`
  - indexes `status`, `match`, and `assert` checks across feature files
- `call_read_deep_context(project_name, feature_path, scenario_tag, scenario_name, node_id, max_depth, limit)`
  - expands nested `call read(...)` chains, including target feature/scenario context
- `ai_feature_context_pack(project_name, feature_path, scenario_tag, scenario_name, node_id, max_call_depth, limit)`
  - returns an AI-ready pack with intent, variable flow, assertions, call/read chain, and graph context
- `feature_behavior_map(project_name, feature_path, scenario_tag, scenario_name, node_id, limit)`
  - groups scenario behavior into preconditions, actions, expectations, plus data inputs and status expectations
- `scenario_similarity_map(project_name, query, limit, top_k)`
  - finds similar scenarios by intent-keyword overlap to improve reuse and AI suggestion quality
- `feature_reuse_advisor(project_name, min_group_size, min_flow_length, limit, include_low_signal)`
  - finds duplicate steps and repeated flows, indexes their locations, and returns AI-safe refactor plans

## DB Understanding For AI

These tools help AI understand query usage, variable flow, and DB-related impact:

- `db_query_index(project_name, query, limit, include_components)`
  - indexes DB query nodes and DB executor/components with operation/table/database/host/risk/usage
- `search_db_usage(project_name, query, limit)`
  - searches DB usage by table, operation, host, file path, or query keywords
- `db_data_flow_trace(project_name, feature_path, scenario_tag, scenario_name, node_id, limit)`
  - traces DB-related variables, DB call steps, and DB assertions inside selected scenarios
- `db_assertion_map(project_name, query, limit)`
  - indexes DB-related assertion steps and links them to DB variables/query signatures
- `db_impact_preview(project_name, changed_entities, limit)`
  - previews impacted test cases from changed DB entities (tables/schemas/hosts/DB feature paths)

## Visual Reports

Interactive HTML graph output is generated under each project `output/` folder.

- Test cases are shown as `@TEST-ID - Scenario name` when Jira/test-case tags exist.
- Dashboard search supports `TEST-ID`, `@TEST-ID`, scenario name, component name, and feature path.

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
