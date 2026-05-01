# Implementation Plan: Karate Feature Graph Analyzer

## Overview

This implementation plan breaks down the Karate Feature Graph Analyzer MCP tool into discrete coding tasks. The tool will be implemented in Python, following the architecture and design specified in the design document. The implementation follows an incremental approach: core parsing → graph construction → analysis capabilities → MCP interface → optimization features.

## Tasks

- [x] 1. Set up project structure and core dependencies
  - Create Python package structure with modules: parser, graph, analyzer, mcp_interface, storage, cache, visualization
  - Set up pyproject.toml with dependencies: hypothesis (property testing), networkx (graph operations), fastapi (MCP server), pydantic (data validation)
  - Configure pytest with hypothesis plugin
  - Create data models module with all dataclasses from design (Scenario, Dependency, Node, Edge, DependencyGraph, etc.)
  - _Requirements: All requirements depend on this foundation_

- [ ] 2. Implement Feature File Parser
  - [x] 2.1 Create Gherkin parser with configurable patterns
    - Implement FeatureFileParser class with parse_file() method
    - Write regex patterns for extracting Scenario and Scenario Outline definitions
    - Implement extract_scenarios() to parse all test case definitions
    - Handle Feature, Background, Scenario, Scenario Outline, Examples blocks
    - _Requirements: 1.1, 1.8_
  
  - [ ]* 2.2 Write property test for complete scenario extraction
    - **Property 1: Complete Scenario Extraction**
    - **Validates: Requirements 1.1**
  
  - [x] 2.3 Implement Jira tag extraction
    - Write configurable regex patterns for Jira tag formats (@PROJ-123, @proj-123, @PROJ_123)
    - Extract tags from Scenario and Scenario Outline annotations
    - Associate tags with corresponding test cases in AST
    - _Requirements: 1.2_
  
  - [ ]* 2.4 Write property test for Jira tag association
    - **Property 2: Jira Tag Association Preservation**
    - **Validates: Requirements 1.2**
  
  - [x] 2.5 Implement dependency extraction
    - Parse "call read()" statements (single-line and multi-line)
    - Extract URL references from API calls (explicit strings and variables)
    - Identify page object references from configured directories
    - Extract database operation keywords (SQL, database interaction statements)
    - Implement resolve_path() for relative path resolution
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 9.4, 9.5_
  
  - [ ]* 2.6 Write property test for dependency extraction
    - **Property 3: Dependency Extraction Completeness**
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6**
  
  - [x] 2.7 Implement Scenario Outline structure preservation
    - Parse Examples blocks and associate with parent Scenario Outline
    - Preserve parent-child relationships in AST
    - Inherit Jira tags from parent to Examples
    - _Requirements: 1.8_
  
  - [ ]* 2.8 Write property test for Scenario Outline structure
    - **Property 4: Scenario Outline Structure Preservation**
    - **Validates: Requirements 1.8**
  
  - [x] 2.9 Implement error handling for malformed files
    - Catch parsing exceptions and return structured ParseError
    - Include file path, line number, and error description
    - Implement graceful degradation for unresolved references
    - _Requirements: 1.7, 9.7_
  
  - [ ]* 2.10 Write property test for graceful error handling
    - **Property 5: Graceful Error Handling**
    - **Validates: Requirements 1.7**
  
  - [ ]* 2.11 Write unit tests for parser edge cases
    - Test empty files, files with only comments, single-scenario files
    - Test unclosed strings, invalid keywords, malformed tags
    - Test specific Jira tag format variations

- [x] 3. Checkpoint - Ensure parser tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement Graph Builder
  - [x] 4.1 Create GraphBuilder class with node creation
    - Implement add_test_case() to create test case nodes
    - Create nodes for workflows, API calls, page objects, database operations
    - Store node metadata (file path, line numbers, Jira tags, project name)
    - Use networkx DiGraph as underlying graph structure
    - _Requirements: 2.1, 2.6_
  
  - [ ]* 4.2 Write property test for complete node creation
    - **Property 6: Complete Node Creation**
    - **Validates: Requirements 2.1**
  
  - [x] 4.3 Implement edge creation for dependencies
    - Implement add_dependency() to create directed edges
    - Create edges for workflow calls (TEST_CASE → WORKFLOW)
    - Create edges for page references (TEST_CASE/WORKFLOW → PAGE)
    - Create edges for API calls (TEST_CASE/WORKFLOW → API)
    - Create edges for database operations (TEST_CASE/WORKFLOW → DATABASE)
    - Store edge metadata (dependency type)
    - _Requirements: 2.2, 2.3, 2.4, 2.5_
  
  - [ ]* 4.4 Write property test for dependency edge creation
    - **Property 7: Dependency Edge Creation**
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5**
  
  - [ ]* 4.5 Write property test for node metadata completeness
    - **Property 8: Node Metadata Completeness**
    - **Validates: Requirements 2.6**
  
  - [x] 4.6 Implement circular dependency detection
    - Implement detect_cycles() using DFS algorithm
    - Mark detected cycles in graph metadata
    - Return list of cycle paths
    - _Requirements: 2.7_
  
  - [ ]* 4.7 Write property test for circular dependency detection
    - **Property 9: Circular Dependency Detection**
    - **Validates: Requirements 2.7**
  
  - [x] 4.8 Implement build_from_project() orchestration
    - Coordinate parsing of all feature files in project
    - Build complete graph from parsed ASTs
    - Handle parsing errors gracefully
    - Return DependencyGraph object
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
  
  - [ ]* 4.9 Write unit tests for graph builder edge cases
    - Test empty graphs, single-node graphs, self-referencing prevention
    - Test graphs with only test cases (no dependencies)

- [x] 5. Checkpoint - Ensure graph builder tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement Project Registry
  - [x] 6.1 Create Project and ProjectRegistry classes
    - Implement Project dataclass with name, root_path, feature_file_patterns, parser_config
    - Implement ProjectRegistry with add, remove, list, get operations
    - Validate project paths exist and contain feature files
    - _Requirements: 3.1, 3.2, 3.4_
  
  - [ ]* 6.2 Write property test for project configuration round-trip
    - **Property 11: Project Configuration Round-Trip**
    - **Validates: Requirements 3.1, 3.6**
  
  - [ ]* 6.3 Write property test for project path validation
    - **Property 12: Project Path Validation**
    - **Validates: Requirements 3.2**
  
  - [x] 6.4 Implement feature file indexing
    - Scan project directory for feature files matching patterns
    - Support glob patterns (*.feature, **/*.feature)
    - Return list of discovered feature file paths
    - _Requirements: 3.3_
  
  - [ ]* 6.5 Write property test for complete feature file indexing
    - **Property 13: Complete Feature File Indexing**
    - **Validates: Requirements 3.3**
  
  - [ ]* 6.6 Write property test for project registry CRUD correctness
    - **Property 14: Project Registry CRUD Correctness**
    - **Validates: Requirements 3.4**
  
  - [x] 6.7 Implement persistent storage for project registry
    - Store project configurations to JSON file
    - Load configurations on startup
    - Implement atomic writes to prevent corruption
    - _Requirements: 3.6_
  
  - [ ]* 6.8 Write property test for project graph isolation
    - **Property 15: Project Graph Isolation**
    - **Validates: Requirements 3.5, 3.7**

- [ ] 7. Implement Dependency Analyzer
  - [x] 7.1 Create DependencyAnalyzer class with query capabilities
    - Initialize with DependencyGraph
    - Implement find_dependencies() for direct and transitive dependencies
    - Use networkx graph traversal algorithms
    - _Requirements: 2.8, 6.4_
  
  - [ ]* 7.2 Write property test for query result correctness
    - **Property 10: Query Result Correctness**
    - **Validates: Requirements 2.8**
  
  - [ ]* 7.3 Write property test for dependency query correctness
    - **Property 28: Dependency Query Correctness**
    - **Validates: Requirements 6.4**
  
  - [x] 7.4 Implement impact analysis
    - Implement impact_analysis() to find all affected test cases
    - Perform reverse graph traversal from component to test cases
    - Calculate dependency paths from test cases to changed component
    - Calculate depth for each dependency relationship
    - Return ImpactResult with affected test cases, paths, depths, Jira tags
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_
  
  - [ ]* 7.5 Write property test for transitive impact analysis completeness
    - **Property 22: Transitive Impact Analysis Completeness**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 6.5**
  
  - [ ]* 7.6 Write property test for impact analysis path validity
    - **Property 23: Impact Analysis Path Validity**
    - **Validates: Requirements 5.5**
  
  - [ ]* 7.7 Write property test for impact analysis metadata inclusion
    - **Property 24: Impact Analysis Metadata Inclusion**
    - **Validates: Requirements 5.6**
  
  - [ ]* 7.8 Write property test for dependency depth calculation
    - **Property 25: Dependency Depth Calculation Correctness**
    - **Validates: Requirements 5.7**
  
  - [x] 7.9 Implement common component identification
    - Implement find_common_components() across multiple projects
    - Identify workflows, APIs, pages with matching identifiers
    - Calculate usage frequency for each component
    - Rank components by usage frequency
    - Return ReusableComponent objects with metadata
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
  
  - [ ]* 7.10 Write property test for common component identification
    - **Property 29: Common Component Identification Correctness**
    - **Validates: Requirements 6.7, 7.1, 7.2, 7.3, 7.7**
  
  - [ ]* 7.11 Write property test for usage frequency calculation
    - **Property 32: Usage Frequency Calculation Correctness**
    - **Validates: Requirements 7.4**
  
  - [ ]* 7.12 Write property test for reusable component ranking
    - **Property 33: Reusable Component Ranking Correctness**
    - **Validates: Requirements 7.5**
  
  - [ ]* 7.13 Write property test for reusable component metadata
    - **Property 34: Reusable Component Metadata Completeness**
    - **Validates: Requirements 7.6**
  
  - [ ]* 7.14 Write unit tests for analyzer edge cases
    - Test impact analysis on leaf nodes, root nodes
    - Test queries on empty graphs, queries with no matches

- [x] 8. Checkpoint - Ensure analyzer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement Inverted Indices and Cache
  - [x] 9.1 Create InvertedIndices class
    - Build jira_tag_index mapping tags to node IDs
    - Build api_endpoint_index mapping endpoints to node IDs
    - Build page_object_index mapping pages to node IDs
    - Build database_op_index mapping operations to node IDs
    - Implement O(1) lookup methods
    - _Requirements: 10.1, 10.2_
  
  - [ ]* 9.2 Write property test for inverted index correctness
    - **Property 45: Inverted Index Correctness**
    - **Validates: Requirements 10.1, 10.2**
  
  - [x] 9.3 Create CacheManager class
    - Implement LRU cache for parsed ASTs
    - Key by file path and modification timestamp
    - Implement cache invalidation on file changes
    - Detect file changes through timestamp comparison
    - _Requirements: 10.3_
  
  - [ ]* 9.4 Write property test for AST cache hit correctness
    - **Property 46: AST Cache Hit Correctness**
    - **Validates: Requirements 10.3**
  
  - [x] 9.5 Implement incremental graph updates
    - Detect changed files since last analysis
    - Update only affected nodes and edges
    - Rebuild inverted indices for changed components
    - _Requirements: 10.6_
  
  - [ ]* 9.6 Write property test for incremental graph update correctness
    - **Property 49: Incremental Graph Update Correctness**
    - **Validates: Requirements 10.6**

- [ ] 10. Implement MCP Interface Layer
  - [x] 10.1 Create KarateGraphAnalyzerTool class with MCP protocol
    - Set up FastAPI or MCP server framework
    - Define MCP tool schema and function signatures
    - Implement input parameter validation using Pydantic
    - _Requirements: 6.8, 6.9_
  
  - [x] 10.2 Implement register_project MCP function
    - Accept project name and root path parameters
    - Validate parameters and call ProjectRegistry.add()
    - Return success/error response in JSON format
    - _Requirements: 6.1_
  
  - [ ]* 10.3 Write property test for MCP response JSON validity
    - **Property 30: MCP Response JSON Validity**
    - **Validates: Requirements 6.8**
  
  - [x] 10.4 Implement list_projects MCP function
    - Call ProjectRegistry.list()
    - Return list of ProjectInfo objects
    - _Requirements: 6.2_
  
  - [ ]* 10.5 Write property test for project listing completeness
    - **Property 26: Project Listing Completeness**
    - **Validates: Requirements 6.2**
  
  - [x] 10.6 Implement analyze_project MCP function
    - Accept project name parameter
    - Call GraphBuilder.build_from_project()
    - Return AnalysisResult with graph statistics
    - _Requirements: 6.3_
  
  - [ ]* 10.7 Write property test for project analysis graph validity
    - **Property 27: Project Analysis Graph Validity**
    - **Validates: Requirements 6.3**
  
  - [x] 10.8 Implement query_dependencies MCP function
    - Accept component ID and transitive flag
    - Call DependencyAnalyzer.find_dependencies()
    - Return DependencyResult in JSON format
    - _Requirements: 6.4_
  
  - [x] 10.9 Implement impact_analysis MCP function
    - Accept component ID parameter
    - Call DependencyAnalyzer.impact_analysis()
    - Return ImpactResult with affected test cases
    - _Requirements: 6.5_
  
  - [x] 10.10 Implement get_node_details MCP function
    - Accept node ID parameter
    - Retrieve node from graph
    - Return NodeDetails with complete metadata
    - _Requirements: 6.6_
  
  - [ ]* 10.11 Write property test for node details retrieval completeness
    - **Property 16: Node Details Retrieval Completeness**
    - **Validates: Requirements 4.2, 6.6**
  
  - [x] 10.12 Implement find_common_components MCP function
    - Accept list of project names
    - Call DependencyAnalyzer.find_common_components()
    - Return list of ReusableComponent objects
    - _Requirements: 6.7_
  
  - [x] 10.13 Implement export_graph and import_graph MCP functions
    - Accept format parameter (JSON or GraphML)
    - Implement JSON serialization of DependencyGraph
    - Implement GraphML export using networkx
    - Implement import with validation
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_
  
  - [ ]* 10.14 Write property test for graph export completeness
    - **Property 35: Graph Export Completeness**
    - **Validates: Requirements 8.1, 8.2, 8.7**
  
  - [ ]* 10.15 Write property test for graph import/export round-trip
    - **Property 36: Graph Import/Export Round-Trip**
    - **Validates: Requirements 8.3, 8.4**
  
  - [ ]* 10.16 Write property test for graph import validation
    - **Property 37: Graph Import Validation**
    - **Validates: Requirements 8.5, 8.6**
  
  - [x] 10.17 Implement error handling for all MCP functions
    - Return structured error responses with error codes
    - Map internal exceptions to MCP error codes (1xxx-6xxx)
    - Include descriptive error messages and details
    - _Requirements: 6.9_
  
  - [ ]* 10.18 Write property test for structured error response
    - **Property 31: Structured Error Response**
    - **Validates: Requirements 6.9**
  
  - [ ]* 10.19 Write unit tests for MCP interface
    - Test function signature validation
    - Test JSON serialization of complex objects
    - Test error response formatting
    - Test batch query with empty batch

- [x] 11. Checkpoint - Ensure MCP interface tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Implement Configurable Parsing Rules
  - [x] 12.1 Create ParserConfig dataclass
    - Define fields: jira_tag_patterns, workflow_directories, page_object_directories, variable_patterns, api_extraction_rules
    - Implement default configuration
    - _Requirements: 9.1, 9.2, 9.3, 9.6_
  
  - [x] 12.2 Integrate ParserConfig into FeatureFileParser
    - Accept ParserConfig in constructor
    - Apply configurable regex patterns for Jira tags
    - Apply configurable path resolution rules
    - Apply configurable variable patterns
    - _Requirements: 9.1, 9.2, 9.3, 9.6_
  
  - [ ]* 12.3 Write property test for configurable tag pattern extraction
    - **Property 38: Configurable Tag Pattern Extraction**
    - **Validates: Requirements 9.1**
  
  - [ ]* 12.4 Write property test for variable path resolution
    - **Property 39: Variable Path Resolution**
    - **Validates: Requirements 9.2**
  
  - [ ]* 12.5 Write property test for configurable path resolution
    - **Property 40: Configurable Path Resolution**
    - **Validates: Requirements 9.3**
  
  - [ ]* 12.6 Write property test for multi-line call statement parsing
    - **Property 41: Multi-Line Call Statement Parsing**
    - **Validates: Requirements 9.4**
  
  - [ ]* 12.7 Write property test for variable URL extraction
    - **Property 42: Variable URL Extraction**
    - **Validates: Requirements 9.5**
  
  - [ ]* 12.8 Write property test for custom parsing rule application
    - **Property 43: Custom Parsing Rule Application**
    - **Validates: Requirements 9.6**
  
  - [ ]* 12.9 Write property test for unresolved reference tolerance
    - **Property 44: Unresolved Reference Tolerance**
    - **Validates: Requirements 9.7**

- [ ] 13. Implement Graph Visualizer
  - [x] 13.1 Create GraphVisualizer class
    - Choose visualization library (pyvis, plotly, or d3.js via HTML generation)
    - Implement render() method to generate interactive HTML
    - Apply different colors/shapes for node types
    - _Requirements: 4.1, 4.7_
  
  - [ ]* 13.2 Write property test for visual node type distinction
    - **Property 20: Visual Node Type Distinction**
    - **Validates: Requirements 4.7**
  
  - [ ] 13.3 Implement node interaction features
    - Display node details on click (file path, line numbers, Jira tags)
    - Highlight selected node and direct dependencies
    - _Requirements: 4.2, 4.5_
  
  - [ ] 13.4 Implement filtering and search
    - Filter nodes by type (TEST_CASE, WORKFLOW, API, PAGE, DATABASE)
    - Search nodes by name or Jira tag
    - _Requirements: 4.3, 4.4_
  
  - [ ]* 13.5 Write property test for type filter correctness
    - **Property 17: Type Filter Correctness**
    - **Validates: Requirements 4.3**
  
  - [ ]* 13.6 Write property test for search result correctness
    - **Property 18: Search Result Correctness**
    - **Validates: Requirements 4.4**
  
  - [ ]* 13.7 Write property test for dependency highlight set correctness
    - **Property 19: Dependency Highlight Set Correctness**
    - **Validates: Requirements 4.5**
  
  - [ ] 13.8 Implement zoom, pan, and layout controls
    - Support zoom and pan interactions
    - Implement layout algorithms (force-directed, hierarchical)
    - _Requirements: 4.6_
  
  - [ ] 13.9 Implement circular dependency visualization
    - Visually indicate cycles with distinct styling
    - Highlight cycle paths when selected
    - _Requirements: 4.8_
  
  - [ ]* 13.10 Write property test for cycle visualization indication
    - **Property 21: Cycle Visualization Indication**
    - **Validates: Requirements 4.8**

- [ ] 14. Implement AI Agent Optimization Features
  - [ ] 14.1 Implement code section retrieval
    - Accept node ID and return file path with line range
    - Include configurable surrounding context lines
    - _Requirements: 10.4, 10.7_
  
  - [ ]* 14.2 Write property test for code section response accuracy
    - **Property 47: Code Section Response Accuracy**
    - **Validates: Requirements 10.4**
  
  - [ ]* 14.3 Write property test for code snippet context inclusion
    - **Property 50: Code Snippet Context Inclusion**
    - **Validates: Requirements 10.7**
  
  - [ ] 14.2 Implement batch query support
    - Accept list of node IDs or queries
    - Return all results in single response
    - Optimize to avoid redundant graph traversals
    - _Requirements: 10.5_
  
  - [ ]* 14.5 Write property test for batch query completeness
    - **Property 48: Batch Query Completeness**
    - **Validates: Requirements 10.5**

- [x] 15. Checkpoint - Ensure all feature tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 16. Integration and End-to-End Testing
  - [ ]* 16.1 Write integration tests for file system operations
    - Test reading feature files from disk
    - Test writing project registry to disk
    - Test exporting graphs to files
    - Test detecting file changes via timestamps
  
  - [ ]* 16.2 Write integration tests for multi-project workflows
    - Test registering multiple projects
    - Test analyzing projects in parallel
    - Test finding common components across projects
    - Test project isolation verification
  
  - [ ]* 16.3 Write integration tests for visualization
    - Test rendering graphs with visualization library
    - Test generating interactive HTML output
    - Test handling large graphs (1000+ nodes)
  
  - [ ]* 16.4 Write performance integration tests
    - Test query response time on 10,000-node graphs (< 100ms requirement)
    - Test incremental update performance vs. full re-analysis
    - Measure cache hit rate
    - Measure memory usage with large graphs
  
  - [ ]* 16.5 Write end-to-end workflow tests
    - Test complete workflow: register project → analyze → query → impact analysis → export
    - Test error recovery scenarios
    - Test concurrent access to project registry

- [ ] 17. Documentation and Deployment Preparation
  - [x] 17.1 Create README with usage examples
    - Document MCP tool installation
    - Provide example MCP function calls
    - Document configuration options
    - Include troubleshooting guide
  
  - [x] 17.2 Create API documentation
    - Document all MCP functions with parameters and return types
    - Document error codes and meanings
    - Provide example requests and responses
  
  - [x] 17.3 Set up logging configuration
    - Configure structured logging with DEBUG, INFO, WARN, ERROR, CRITICAL levels
    - Include timestamps, component names, and contextual data
    - Set up log rotation and retention policies
  
  - [x] 17.4 Create deployment package
    - Set up pyproject.toml with all dependencies
    - Create entry point for MCP server
    - Include sample project configurations
    - Create Docker container (optional)

- [x] 18. Final checkpoint - Ensure all tests pass and documentation is complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation throughout implementation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Integration tests verify end-to-end workflows and performance requirements
- The implementation uses Python with Hypothesis for property-based testing
- Core dependencies: networkx (graphs), hypothesis (testing), fastapi/pydantic (MCP interface)
- All 50 correctness properties from the design document are covered by property tests
