
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

    def extract_java_usages(self, steps: List[Step], all_aliases: Dict[str, str]) -> List[Dict[str, str]]:
        """Extract Java class and method usages from a list of steps.
        
        Returns:
            List of dictionaries containing 'class_path' and 'method_name'
        """
        usages = []
        
        # 1. Track variables assigned via 'new' within these steps
        # e.g., * def myObj = new MyClass()
        variable_to_class: Dict[str, str] = {}
        new_var_pattern = r"def\s+(\w+)\s*=\s*new\s+([a-zA-Z0-9_]+)"
        for step in steps:
            new_var_match = re.search(new_var_pattern, step.text)
            if new_var_match:
                var_name, alias = new_var_match.groups()
                if alias in all_aliases:
                    variable_to_class[var_name] = all_aliases[alias]
                    logger.debug(f"Tracked Java variable: {var_name} -> {all_aliases[alias]}")

        for step in steps:
            text = step.text
            
            # 2. Match target.method(...) - target can be alias, variable, or class
            method_pattern = r"([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*\("
            method_matches = re.findall(method_pattern, text)
            for target, method in method_matches:
                class_path = None
                
                # Try to resolve target
                if target in all_aliases:
                    class_path = all_aliases[target]
                elif target in variable_to_class:
                    class_path = variable_to_class[target]
                elif target[0].isupper() and len(target) > 1:
                    # Direct class call (starts with UpperCase)
                    class_path = target
                
                if class_path:
                    usages.append({
                        "class_path": class_path,
                        "method_name": method
                    })
                    logger.debug(f"Detected Java method usage: {class_path}.{method}")

            # 3. Match new Alias(...) - Constructor
            for alias_name, class_path in all_aliases.items():
                new_pattern = rf"new\s+{re.escape(alias_name)}\s*\("
                if re.search(new_pattern, text):
                    # Check if already added (some regex might overlap)
                    if not any(u["class_path"] == class_path and u["method_name"] == "[Constructor]" for u in usages):
                        usages.append({
                            "class_path": class_path,
                            "method_name": "[Constructor]"
                        })
                        logger.debug(f"Detected Java constructor usage: {class_path}")

        return usages
