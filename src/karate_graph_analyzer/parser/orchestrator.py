"""
Dependency Orchestrator for coordinating extractors.

Uses Registry pattern to manage multiple extraction strategies.
"""

from typing import List, Dict, Optional
from karate_graph_analyzer.interfaces import IDependencyExtractor
from karate_graph_analyzer.models import Dependency, ParserConfig


class DependencyOrchestrator:
    """Orchestrates dependency extraction using multiple strategies."""

    def __init__(self, config: ParserConfig):
        self.config = config
        self._extractors: List[IDependencyExtractor] = []

    def register_extractor(self, extractor: IDependencyExtractor):
        """Register a new extraction strategy."""
        self._extractors.append(extractor)

    def extract_from_step(self, step_text: str, line_number: int) -> List[Dependency]:
        """Run all applicable extractors on a step."""
        all_deps = []
        for extractor in self._extractors:
            if extractor.can_extract(step_text):
                deps = extractor.extract(step_text, line_number)
                all_deps.extend(deps)
        return all_deps

    def get_extractor_by_type(self, extractor_class):
        """Get a registered extractor by its class type."""
        for extractor in self._extractors:
            if isinstance(extractor, extractor_class):
                return extractor
        return None
