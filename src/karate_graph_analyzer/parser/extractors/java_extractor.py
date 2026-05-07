
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

    def extract_java_usages(self, scenario: Scenario, all_aliases: Dict[str, str]) -> List[Dict[str, str]]:
        """Extract Java class and method usages from a scenario's steps.
        
        Returns:
            List of dictionaries containing 'class_path' and 'method_name'
        """
        usages = []
        if not all_aliases:
            return usages

        alias_names = list(all_aliases.keys())
        if not alias_names:
            return usages
            
        alias_names.sort(key=len, reverse=True)
        
        for step in scenario.steps:
            text = step.text
            
            for alias in alias_names:
                # 1. Match alias.methodName(...)
                method_pattern = rf"{re.escape(alias)}\.(\w+)"
                method_matches = re.findall(method_pattern, text)
                for method in method_matches:
                    usages.append({
                        "class_path": all_aliases[alias],
                        "method_name": method
                    })
                    logger.debug(f"Detected Java method usage: {all_aliases[alias]}.{method}")

                # 2. Match new alias(...) - method_name will be '<init>'
                new_pattern = rf"new\s+{re.escape(alias)}"
                if re.search(new_pattern, text):
                    usages.append({
                        "class_path": all_aliases[alias],
                        "method_name": "<init>"
                    })
                    logger.debug(f"Detected Java constructor usage: {all_aliases[alias]}")

        # 3. Detect potential direct class calls (e.g. MyUtils.doSomething)
        # even if not in aliases, if it starts with an uppercase letter
        potential_class_pattern = r"([A-Z][a-zA-Z0-9_]*)\.([a-zA-Z0-9_]+)\("
        for step in scenario.steps:
            text = step.text
            class_matches = re.findall(potential_class_pattern, text)
            for class_name, method in class_matches:
                # If it's already caught by an alias, skip it to avoid duplicates
                if any(u.get("class_path") == class_name and u.get("method_name") == method for u in usages):
                    continue
                
                # Check if it's a known alias (could be lowercase alias for uppercase class)
                if class_name in all_aliases:
                    class_path = all_aliases[class_name]
                else:
                    class_path = class_name # Fallback to class name as path
                
                usages.append({
                    "class_path": class_path,
                    "method_name": method
                })
                logger.debug(f"Detected potential Java class usage: {class_path}.{method}")

        return usages
