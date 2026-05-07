import re
from typing import TYPE_CHECKING, Optional, Any, List
from karate_graph_analyzer.models import NodeType, Scenario, ComponentCategory, FlowType

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

        # 1. Check for page object directories (UI Flow) - HIGHEST PRIORITY
        page_dirs = ['pages', 'webpages', 'ui']
        if cfg and cfg.page_object_directories:
            page_dirs = [d.lower() for d in cfg.page_object_directories]
        for d in page_dirs:
            if f'/{d}/' in normalized:
                return NodeType.PAGE

        # 2. Check for database directories (DB Flow)
        db_dirs = ['db', 'database', 'sql']
        if any(f'/{d}/' in normalized for d in db_dirs):
            return NodeType.DATABASE

        # 3. Check for common/API directories (API Flow / Library)
        common_dirs = ['common', 'services', 'api', 'endpoints']
        if cfg and hasattr(cfg, 'common_directories'):
            common_dirs = [d.lower() for d in cfg.common_directories]
        for d in common_dirs:
            if f'/{d}/' in normalized:
                return NodeType.COMMON

        # 4. Check for workflow directories (Test Flow)
        workflow_dirs = ['workflows', 'workflow', 'business-flows']
        if cfg and cfg.workflow_directories:
            workflow_dirs = [d.lower() for d in cfg.workflow_directories]
        for d in workflow_dirs:
            if f'/{d}/' in normalized:
                return NodeType.WORKFLOW
                
        # 5. Check for data directories (Data Flow)
        data_dirs = ['data', 'payloads', 'json', 'csv']
        if any(f'/{d}/' in normalized for d in data_dirs):
            return NodeType.DATA

        # Default: TEST_CASE
        return NodeType.TEST_CASE

    def resolve_flow(self, node_type: Any) -> FlowType:
        """Map a node type to its corresponding architectural flow."""
        # Handle string input or enum
        type_str = node_type.value if hasattr(node_type, 'value') else str(node_type)
        
        mapping = {
            "API": FlowType.API,
            "API_GROUP": FlowType.API,
            "COMMON": FlowType.API,
            "PAGE": FlowType.UI,
            "ACTION": FlowType.UI,
            "LOCATOR": FlowType.UI,
            "DATABASE": FlowType.DATABASE,
            "TEST_CASE": FlowType.TEST,
            "SCENARIO": FlowType.TEST,
            "WORKFLOW": FlowType.TEST,
            "DATA": FlowType.DATA,
        }
        return mapping.get(type_str, FlowType.UNKNOWN)

    def is_infrastructure(self, file_path: str) -> bool:
        """Check if a path belongs to infrastructure/framework code."""
        if not file_path:
            return False
        normalized = file_path.replace('\\', '/').lower()
        
        # Only check the filename and parent folders, not the whole path to avoid project name conflicts
        # Example: E:/Project/karate-core/... shouldn't flag "core"
        parts = normalized.split('/')
        check_path = '/'.join(parts[-4:]) if len(parts) > 4 else normalized
        
        infra_keywords = ['internal', 'framework', 'parallel', 'setup', 'teardown']
        return any(kw in check_path for kw in infra_keywords)

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
            clean_tags = [t for t in scenario.tags if not t.startswith("@ALM2:")]
            if clean_tags:
                return clean_tags[0]
            return scenario.name or f"Unnamed at line {scenario.line_number}"
    
    def detect_business_domain(self, file_path: str, tags: Optional[List[str]] = None) -> str:
        """Detect business domain from tags (priority) or file path (fallback)."""
        # 1. Try to detect from tags first (The "Rule" you mentioned)
        if tags and self.context and self.context.config:
            cfg = self.context.config
            technical_tags = {t.lower() for t in cfg.metadata_tags}
            
            for t in tags:
                # Skip technical tags (like @regression, @smoke)
                if t.lower() in technical_tags:
                    continue
                    
                # Skip Jira/ALM tags using patterns defined in config
                is_metadata = False
                for pattern in cfg.metadata_tag_patterns:
                    if re.match(pattern, t):
                        is_metadata = True
                        break
                
                if not is_metadata:
                    # Found a business tag (e.g., @Lending, @Payment)
                    # Return it cleaned up as the domain
                    return t.lstrip('@').replace('-', ' ').replace('_', ' ').title()

        # 2. Fallback to existing path-based detection
        normalized_path = file_path.replace('\\', '/').lower()
        feature_map = {}
        if self.context and self.context.config:
            feature_map = self.context.config.domain_mapping
        
        path_segments = normalized_path.split('/')
        for segment in path_segments:
            for keyword, domain in feature_map.items():
                if keyword in segment:
                    return domain
        
        if len(path_segments) >= 2:
            parent_dir = path_segments[-2]
            if parent_dir not in ['pages', 'services', 'common', 'workflows', 'features', 'api']:
                return parent_dir.replace('-', ' ').replace('_', ' ').title()
            elif len(path_segments) >= 3:
                parent_dir = path_segments[-3]
                return parent_dir.replace('-', ' ').replace('_', ' ').title()
        
        return "Other"

    def classify_component_category(self, file_path: str) -> ComponentCategory:
        """Classify a component as BUSINESS or INFRASTRUCTURE."""
        if self.is_infrastructure(file_path):
            return ComponentCategory.INFRASTRUCTURE
        return ComponentCategory.BUSINESS
