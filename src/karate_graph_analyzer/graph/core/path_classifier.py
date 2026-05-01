"""
Path Classifier.

Handles classification of Karate feature files and scenarios based on
their file paths and directory structures.
"""

from typing import TYPE_CHECKING
from karate_graph_analyzer.models import NodeType, Scenario

if TYPE_CHECKING:
    from karate_graph_analyzer.models import ParserConfig


class PathClassifier:
    """Classifies scenarios and feature files based on path patterns."""

    def classify_scenario_by_path(
        self, file_path: str, config: "ParserConfig" = None
    ) -> NodeType:
        """Classify a scenario's node type based on its file path."""
        normalized = file_path.replace('\\', '/').lower()

        # Check for page object directories
        page_dirs = ['pages', 'webpages']
        if config and config.page_object_directories:
            page_dirs = [d.lower() for d in config.page_object_directories]
        for d in page_dirs:
            if f'/{d}/' in normalized:
                return NodeType.PAGE

        # Check for workflow directories
        workflow_dirs = ['workflows', 'workflow']
        if config and config.workflow_directories:
            workflow_dirs = [d.lower() for d in config.workflow_directories]
        for d in workflow_dirs:
            if f'/{d}/' in normalized:
                return NodeType.WORKFLOW
                
        # Check for common/API directories
        common_dirs = ['common', 'services']
        if config and hasattr(config, 'common_directories'):
            common_dirs = [d.lower() for d in config.common_directories]
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
        if node_type == NodeType.TEST_CASE:
            if scenario.jira_tags:
                return f"{scenario.jira_tags[0]} - {scenario.name}"
            return scenario.name
        else:
            if scenario.tags:
                return scenario.tags[0]
            return scenario.name or f"Unnamed at line {scenario.line_number}"
    
    def detect_feature_from_path(self, file_path: str) -> str:
        """Detect feature name from file path."""
        import os
        normalized_path = file_path.replace('\\', '/').lower()
        
        exclude_patterns = [
            '/pages/', '/page/', '/services/', '/service/',
            '/common/', '/workflows/', '/workflow/',
        ]
        
        for pattern in exclude_patterns:
            if pattern in normalized_path:
                return None
        
        feature_map = {
            'authentication': 'Authentication', 'auth': 'Authentication', 'login': 'Authentication',
            'orders': 'Order Management', 'order': 'Order Management',
            'products': 'Product Catalog', 'product': 'Product Catalog', 'catalog': 'Product Catalog',
            'users': 'User Management', 'user': 'User Management', 'profile': 'User Management',
            'payments': 'Payment Processing', 'payment': 'Payment Processing', 'checkout': 'Payment Processing',
            'cart': 'Shopping Cart', 'shopping': 'Shopping Cart',
            'search': 'Search', 'notification': 'Notifications', 'notifications': 'Notifications',
            'admin': 'Administration', 'report': 'Reporting', 'reports': 'Reporting', 'analytics': 'Analytics',
        }
        
        path_segments = normalized_path.split('/')
        for segment in path_segments:
            if segment in feature_map:
                return feature_map[segment]
        
        if len(path_segments) >= 2:
            parent_dir = path_segments[-2]
            return parent_dir.replace('-', ' ').replace('_', ' ').title()
        
        return "Other"
