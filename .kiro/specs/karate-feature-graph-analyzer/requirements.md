# Requirements Document

## Introduction

The Karate Feature Graph Analyzer is an MCP (Model Context Protocol) tool built in Python that analyzes Karate Framework feature files and generates interactive dependency graphs. The system enables developers and AI agents to visualize relationships between test cases, workflows, API calls, page objects, and database operations across multiple projects. It provides impact analysis capabilities to identify which test cases are affected when APIs, pages, or database schemas change.

## Glossary

- **Karate_Framework**: A test automation framework that uses Gherkin syntax for API and UI testing
- **Feature_File**: A Gherkin-format file containing test scenarios, typically with .feature extension
- **Test_Case**: A Scenario or Scenario Outline within a Feature_File
- **Workflow**: A reusable feature file called by test cases using the "call read()" syntax
- **Page_Object**: A feature file representing UI page interactions, typically stored in a webPages directory
- **Jira_Tag**: A tag annotation in format @projectkey-number (e.g., @doccdb-1) linking test cases to Jira issues
- **Dependency_Graph**: A directed graph showing relationships between test cases, workflows, APIs, pages, and database operations
- **Impact_Analysis**: The process of identifying which test cases are affected by changes to system components
- **MCP_Tool**: A tool following the Model Context Protocol for AI agent integration
- **Graph_Analyzer**: The core component that parses feature files and builds the dependency graph
- **Graph_Visualizer**: The UI component that renders interactive graph visualizations
- **Project_Registry**: A storage mechanism for managing multiple Karate projects
- **API_Call**: An HTTP request defined in feature files, including URL and endpoint information
- **Database_Operation**: SQL or database interaction statements within feature files

## Requirements

### Requirement 1: Parse Karate Feature Files

**User Story:** As a developer, I want the system to parse Karate feature files, so that I can extract test cases, workflows, and dependencies.

#### Acceptance Criteria

1. WHEN a valid feature file is provided, THE Graph_Analyzer SHALL extract all Scenario and Scenario Outline definitions
2. WHEN a feature file contains Jira_Tags, THE Graph_Analyzer SHALL extract and associate tags with their corresponding test cases
3. WHEN a feature file contains "call read()" statements, THE Graph_Analyzer SHALL extract the called file path and parameters
4. WHEN a feature file contains URL references, THE Graph_Analyzer SHALL extract API endpoint information
5. WHEN a feature file contains page object references, THE Graph_Analyzer SHALL extract page file paths
6. WHEN a feature file contains database operation keywords, THE Graph_Analyzer SHALL extract database interaction details
7. WHEN an invalid or malformed feature file is provided, THE Graph_Analyzer SHALL return a descriptive error message
8. FOR ALL valid feature files, THE Graph_Analyzer SHALL preserve the relationship between Examples blocks and their parent Scenario Outlines with associated Jira_Tags

### Requirement 2: Build Dependency Graph

**User Story:** As a developer, I want the system to build a dependency graph, so that I can understand relationships between test components.

#### Acceptance Criteria

1. WHEN feature files are parsed, THE Graph_Analyzer SHALL create nodes for each Test_Case, Workflow, API_Call, Page_Object, and database operation
2. WHEN a Test_Case calls a Workflow, THE Graph_Analyzer SHALL create a directed edge from the Test_Case to the Workflow
3. WHEN a Test_Case or Workflow references a Page_Object, THE Graph_Analyzer SHALL create a directed edge to the Page_Object
4. WHEN a Test_Case or Workflow makes an API_Call, THE Graph_Analyzer SHALL create a directed edge to the API_Call node
5. WHEN a Test_Case or Workflow performs a database operation, THE Graph_Analyzer SHALL create a directed edge to the database operation node
6. THE Graph_Analyzer SHALL store node metadata including file path, line numbers, and Jira_Tags
7. THE Graph_Analyzer SHALL detect and mark circular dependencies between workflows
8. THE Dependency_Graph SHALL support querying nodes by type, name, or Jira_Tag

### Requirement 3: Manage Multiple Projects

**User Story:** As a developer working on multiple projects, I want to register and manage multiple Karate projects, so that I can analyze dependencies across different codebases.

#### Acceptance Criteria

1. THE Project_Registry SHALL store project configurations including name, root path, and feature file locations
2. WHEN a new project is registered, THE Project_Registry SHALL validate that the root path exists and contains feature files
3. WHEN a project is registered, THE Graph_Analyzer SHALL scan and index all feature files in the project
4. THE Project_Registry SHALL support adding, removing, and listing registered projects
5. WHEN analyzing dependencies, THE MCP_Tool SHALL allow specifying which project to analyze
6. THE Project_Registry SHALL persist project configurations between tool restarts
7. WHEN multiple projects are registered, THE Graph_Analyzer SHALL maintain separate dependency graphs for each project

### Requirement 4: Provide Interactive Graph Visualization

**User Story:** As a developer, I want to view the dependency graph in an interactive UI, so that I can explore relationships visually.

#### Acceptance Criteria

1. THE Graph_Visualizer SHALL render the Dependency_Graph as an interactive web-based visualization
2. WHEN a user clicks on a node, THE Graph_Visualizer SHALL display node details including file path, line numbers, and associated Jira_Tags
3. THE Graph_Visualizer SHALL support filtering nodes by type (Test_Case, Workflow, API_Call, Page_Object, database operation)
4. THE Graph_Visualizer SHALL support searching for nodes by name or Jira_Tag
5. THE Graph_Visualizer SHALL highlight the selected node and its direct dependencies
6. THE Graph_Visualizer SHALL support zooming and panning the graph
7. THE Graph_Visualizer SHALL use different colors or shapes to distinguish node types
8. WHEN a circular dependency exists, THE Graph_Visualizer SHALL visually indicate the cycle

### Requirement 5: Perform Impact Analysis

**User Story:** As a developer, I want to identify which test cases are affected by component changes, so that I can determine testing scope.

#### Acceptance Criteria

1. WHEN an API_Call is specified, THE Graph_Analyzer SHALL return all Test_Cases that directly or transitively depend on that API_Call
2. WHEN a Page_Object is specified, THE Graph_Analyzer SHALL return all Test_Cases that directly or transitively depend on that Page_Object
3. WHEN a database operation is specified, THE Graph_Analyzer SHALL return all Test_Cases that directly or transitively depend on that database operation
4. WHEN a Workflow is specified, THE Graph_Analyzer SHALL return all Test_Cases that directly or transitively call that Workflow
5. THE Graph_Analyzer SHALL include the dependency path showing how each affected Test_Case connects to the changed component
6. THE Graph_Analyzer SHALL return impact analysis results with associated Jira_Tags for affected test cases
7. THE Graph_Analyzer SHALL calculate and return the depth of each dependency relationship

### Requirement 6: Expose MCP Tool Interface

**User Story:** As an AI agent, I want to interact with the graph analyzer through MCP protocol, so that I can retrieve code and analyze dependencies programmatically.

#### Acceptance Criteria

1. THE MCP_Tool SHALL expose a "register_project" function accepting project name and root path
2. THE MCP_Tool SHALL expose a "list_projects" function returning all registered projects
3. THE MCP_Tool SHALL expose a "analyze_project" function that builds the dependency graph for a specified project
4. THE MCP_Tool SHALL expose a "query_dependencies" function accepting a component identifier and returning its dependencies
5. THE MCP_Tool SHALL expose an "impact_analysis" function accepting a component identifier and returning affected test cases
6. THE MCP_Tool SHALL expose a "get_node_details" function returning full metadata for a specified node
7. THE MCP_Tool SHALL expose a "find_common_components" function that identifies reusable workflows, APIs, and pages across projects
8. THE MCP_Tool SHALL return responses in JSON format compatible with MCP protocol
9. WHEN an error occurs, THE MCP_Tool SHALL return structured error messages with error codes and descriptions

### Requirement 7: Identify Reusable Components

**User Story:** As a developer, I want to identify common workflows, APIs, and pages across projects, so that I can maximize code reuse.

#### Acceptance Criteria

1. WHEN multiple projects are registered, THE Graph_Analyzer SHALL identify Workflows with identical or similar names across projects
2. WHEN multiple projects are registered, THE Graph_Analyzer SHALL identify API_Calls with identical endpoints across projects
3. WHEN multiple projects are registered, THE Graph_Analyzer SHALL identify Page_Objects with identical or similar names across projects
4. THE Graph_Analyzer SHALL calculate usage frequency for each reusable component
5. THE MCP_Tool SHALL return a ranked list of reusable components sorted by usage frequency
6. THE MCP_Tool SHALL provide file paths and project names for each reusable component instance
7. THE Graph_Analyzer SHALL detect functionally equivalent components with different names based on their dependencies

### Requirement 8: Export and Import Graph Data

**User Story:** As a developer, I want to export and import graph data, so that I can share analysis results and persist graph state.

#### Acceptance Criteria

1. THE Graph_Analyzer SHALL export the Dependency_Graph to JSON format including all nodes, edges, and metadata
2. THE Graph_Analyzer SHALL export the Dependency_Graph to GraphML format for compatibility with external graph tools
3. WHEN a valid JSON graph export is provided, THE Graph_Analyzer SHALL import and reconstruct the Dependency_Graph
4. WHEN a valid GraphML export is provided, THE Graph_Analyzer SHALL import and reconstruct the Dependency_Graph
5. THE Graph_Analyzer SHALL validate imported graph data for structural integrity
6. WHEN imported graph data is invalid, THE Graph_Analyzer SHALL return a descriptive error message
7. THE exported graph data SHALL include project metadata and timestamp information

### Requirement 9: Handle Karate Syntax Variations

**User Story:** As a developer working with different Karate project styles, I want the parser to handle syntax variations, so that it works across different codebases.

#### Acceptance Criteria

1. WHEN feature files use different Jira_Tag formats, THE Graph_Analyzer SHALL extract tags matching configurable regex patterns
2. WHEN feature files use variable expressions in "call read()" paths, THE Graph_Analyzer SHALL resolve paths using common variable patterns
3. WHEN feature files use different directory structures for workflows and pages, THE Graph_Analyzer SHALL support configurable path resolution rules
4. THE Graph_Analyzer SHALL handle both single-line and multi-line "call read()" statements
5. THE Graph_Analyzer SHALL extract API information from both explicit URL strings and variable references
6. WHEN a project configuration specifies custom parsing rules, THE Graph_Analyzer SHALL apply those rules during analysis
7. THE Graph_Analyzer SHALL log warnings for unresolved references without failing the entire analysis

### Requirement 10: Optimize for AI Agent Access

**User Story:** As an AI agent, I want fast access to relevant code sections, so that I can quickly understand and generate test code.

#### Acceptance Criteria

1. THE Graph_Analyzer SHALL build an inverted index mapping Jira_Tags to Test_Cases for fast lookup
2. THE Graph_Analyzer SHALL build an inverted index mapping API endpoints to Test_Cases for fast lookup
3. THE Graph_Analyzer SHALL cache parsed feature file ASTs to avoid re-parsing unchanged files
4. WHEN a code section is requested, THE MCP_Tool SHALL return the exact file path and line range
5. THE MCP_Tool SHALL support batch queries to retrieve multiple code sections in a single request
6. THE Graph_Analyzer SHALL detect file changes and incrementally update the graph without full re-analysis
7. THE MCP_Tool SHALL return code snippets with surrounding context when requested
8. THE Graph_Analyzer SHALL maintain response time under 100ms for single node queries on graphs with up to 10,000 nodes

