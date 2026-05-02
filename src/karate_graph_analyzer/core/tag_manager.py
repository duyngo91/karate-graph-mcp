import re
from typing import List, Optional
from karate_graph_analyzer.models import ParserConfig

class TagManager:
    """Specialized service for tag categorization and filtering."""

    def __init__(self, config: Optional[ParserConfig] = None) -> None:
        self.config = config or ParserConfig()

    def normalize_tag(self, tag: str) -> str:
        """Ensure tag starts with @."""
        if not tag:
            return ""
        return tag if tag.startswith("@") else f"@{tag}"

    def is_metadata_tag(self, tag: str) -> bool:
        """Check if a tag is a metadata/technical tag that should be filtered out."""
        clean_tag = self.normalize_tag(tag)
        
        if clean_tag in self.config.metadata_tags:
            return True
            
        return any(re.match(pattern, clean_tag) for pattern in self.config.metadata_tag_patterns)

    def filter_functional_tags(self, tags: List[str]) -> List[str]:
        """Return only tags that are not metadata tags."""
        return [t for t in tags if not self.is_metadata_tag(t)]

    def get_primary_tag(self, tags: List[str]) -> str:
        """Get the first functional tag to use as a unique identifier."""
        functional = self.filter_functional_tags(tags)
        if functional:
            # Return raw tag for identity, normalized to start with @
            return self.normalize_tag(functional[0])
        return ""

    def get_display_tag(self, tags: List[str]) -> str:
        """Get the primary functional tag for display, or empty string."""
        functional = self.filter_functional_tags(tags)
        if functional:
            return self.normalize_tag(functional[0])
        return ""
