"""
Path Classifier.

Handles classification of Karate feature files and scenarios based on
their file paths and directory structures.
"""

from typing import TYPE_CHECKING
from karate_graph_analyzer.models import NodeType, Scenario
from typing import Optional

if TYPE_CHECKING:
    from karate_graph_analyzer.core.context import AnalysisContext


class PathClassifier:
    """Classifies scenarios and feature files based on path patterns."""

    def __init__(self, context: Optional["AnalysisContext"] = None) -> None:
        self.context = context

    def classify_scenario_by_path(
        self, file_path: str, config=None
    ) -> NodeType:
        """Classify a scenario's node type based on its file path."""
        # Use context config if available
        cfg = config or (self.context.config if self.context else None)
        normalized = file_path.replace('\\', '/').lower()

        # Check for page object directories
        page_dirs = ['pages', 'webpages']
        if cfg and cfg.page_object_directories:
            page_dirs = [d.lower() for d in cfg.page_object_directories]
        for d in page_dirs:
            if f'/{d}/' in normalized:
                return NodeType.PAGE

        # Check for workflow directories
        workflow_dirs = ['workflows', 'workflow']
        if cfg and cfg.workflow_directories:
            workflow_dirs = [d.lower() for d in cfg.workflow_directories]
        for d in workflow_dirs:
            if f'/{d}/' in normalized:
                return NodeType.WORKFLOW
                
        # Check for common/API directories
        common_dirs = ['common', 'services']
        if cfg and hasattr(cfg, 'common_directories'):
            common_dirs = [d.lower() for d in cfg.common_directories]
        for d in common_dirs:
            if f'/{d}/' in normalized:
                return NodeType.COMMON

        # Check for database directories
        if '/db/' in normalized or '/database/' in normalized:
            return NodeType.DATABASE

        # Default: TEST_CASE
        return NodeType.TEST_CASE

    def build_scenario_display_name(self, scenario: Scenario, node_type: NodeType) -> str:
        """Build display name for a scenario based on its node type."""
        if self.context and self.context.tag_manager:
            tag_str = self.context.tag_manager.get_display_tag(scenario.tags)
            if scenario.name.strip():
                return f"{tag_str} - {scenario.name}" if tag_str else scenario.name
            return tag_str or scenario.name or f"Unnamed at line {scenario.line_number}"

        # Fallback if no context
        if node_type == NodeType.TEST_CASE:
            if scenario.jira_tags:
                return f"{scenario.jira_tags[0]} - {scenario.name}"
            return scenario.name
        else:
            # Simple fallback filter
            clean_tags = [t for t in scenario.tags if not t.startswith("@ALM2:")]
            if clean_tags:
                return clean_tags[0]
            return scenario.name or f"Unnamed at line {scenario.line_number}"
    
    def detect_business_domain(self, file_path: str) -> str:
        """
        Detect business domain from file path regardless of component type.
        Used for grouping and statistics.
        """
        normalized_path = file_path.replace('\\', '/').lower()
        
        # Get mapping from config
        feature_map = {}
        if self.context and self.context.config:
            feature_map = self.context.config.domain_mapping
        
        path_segments = normalized_path.split('/')
        
        # 1. Try keyword matching in segments
        for segment in path_segments:
            for keyword, domain in feature_map.items():
                if keyword in segment:
                    return domain
        
        # 2. Fallback to parent directory name if keyword matching fails
        if len(path_segments) >= 2:
            parent_dir = path_segments[-2]
            if parent_dir not in ['pages', 'services', 'common', 'workflows', 'features']:
                return parent_dir.replace('-', ' ').replace('_', ' ').title()
            elif len(path_segments) >= 3:
                # Try one level higher
                parent_dir = path_segments[-3]
                return parent_dir.replace('-', ' ').replace('_', ' ').title()
        
        return "Other"

    def detect_feature_from_path(self, file_path: str) -> Optional[str]:
        """
        Detect feature name for test cases. 
        Returns None for shared components (pages, common, etc).
        """
        normalized_path = file_path.replace('\\', '/').lower()
        
        exclude_patterns = [
            '/pages/', '/page/', '/services/', '/service/',
            '/common/', '/workflows/', '/workflow/',
        ]
        
        for pattern in exclude_patterns:
            if pattern in normalized_path:
                return None
        
        return self.detect_business_domain(file_path)
