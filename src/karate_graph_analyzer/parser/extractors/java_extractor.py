
import re
import logging
from typing import Dict, List, Set, Optional
from karate_graph_analyzer.models import Scenario, Dependency

logger = logging.getLogger(__name__)

class JavaExtractor:
    """Extracts Java class references and usages from Karate features."""

    def __init__(self):
        # Local aliases within a feature file
        self.local_aliases: Dict[str, str] = {}
        
    def can_extract(self, step_text: str) -> bool:
        """Check if this step contains a Java declaration or usage."""
        return "Java.type" in step_text or "new " in step_text or "." in step_text

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        """Manual extraction is handled in FeatureFileParser for better context tracking.
        This method returns empty list to avoid duplicate dependencies if called by orchestrator.
        """
        return []

    def extract_local_aliases(self, content: str) -> Dict[str, str]:
        """Extract Java.type aliases from feature content.
        
        Example: * def Utils = Java.type('com.company.Utils')
        """
        aliases = {}
        # Pattern: def alias = Java.type('...')
        pattern = r"def\s+(\w+)\s*=\s*Java\.type\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
        matches = re.findall(pattern, content)
        for alias, class_path in matches:
            aliases[alias] = class_path
            self.local_aliases[alias] = class_path
            logger.debug(f"Extracted local Java alias: {alias} -> {class_path}")
        return aliases

    def extract_java_usages(self, scenario: Scenario, all_aliases: Dict[str, str]) -> Set[str]:
        """Extract Java class usages from a scenario's steps.
        
        Matches:
        - alias.method()
        - new alias()
        
        Args:
            scenario: The scenario to analyze
            all_aliases: Merged dictionary of global and local aliases
            
        Returns:
            Set of Java class paths used in this scenario
        """
        used_classes = set()
        if not all_aliases:
            return used_classes

        # Create a regex pattern to match any of the aliases followed by . or used with new
        alias_names = list(all_aliases.keys())
        if not alias_names:
            return used_classes
            
        # Sort alias names by length descending to match longest first (e.g. MyUtils vs MyUtilsSpecial)
        alias_names.sort(key=len, reverse=True)
        
        # Pattern for usage: alias.method or new alias
        # We look for words followed by . or preceded by new
        for step in scenario.steps:
            text = step.text
            
            # Check for alias.method()
            for alias in alias_names:
                # Use word boundary to avoid partial matches
                if re.search(rf"\b{re.escape(alias)}\.", text) or re.search(rf"\bnew\s+{re.escape(alias)}\b", text):
                    used_classes.add(all_aliases[alias])
                    logger.debug(f"Detected Java usage in scenario '{scenario.name}': {alias} -> {all_aliases[alias]}")

        return used_classes
