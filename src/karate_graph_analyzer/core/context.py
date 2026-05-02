from typing import Optional
from karate_graph_analyzer.models import Project, ParserConfig
from karate_graph_analyzer.core.tag_manager import TagManager

class AnalysisContext:
    """Central context for a scanning session.
    
    Provides access to configuration and common services.
    """

    def __init__(self, project: Project) -> None:
        self.project = project
        self.config = project.parser_config
        self.tag_manager = TagManager(self.config)

    @classmethod
    def create_default(cls) -> "AnalysisContext":
        """Create a default context for testing or simple scans."""
        dummy_project = Project(name="Default", root_path=".")
        return cls(dummy_project)
