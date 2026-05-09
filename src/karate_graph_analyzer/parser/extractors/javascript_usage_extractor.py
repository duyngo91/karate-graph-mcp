"""Extract JavaScript helper aliases and function usages from Karate steps."""

import re
from typing import Dict, List

from karate_graph_analyzer.models import ParserConfig, Step


class JavaScriptUsageExtractor:
    """Track `read('*.js')` aliases and calls such as `helper.sign()`."""

    _ALIAS_PATTERN = re.compile(
        r"\bdef\s+([A-Za-z_$][\w$]*)\s*=\s*(?:call\s+)?(?:read|karate\.read)\s*\(\s*['\"]([^'\"]+\.js(?:#[^'\"]+)?)['\"]",
        re.IGNORECASE,
    )
    _CALL_PATTERN = re.compile(r"\b([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*\(")

    def __init__(self, config: ParserConfig) -> None:
        self.config = config
        self.local_aliases: Dict[str, str] = {}

    def extract_aliases(self, step_text: str) -> Dict[str, str]:
        aliases = {}
        for alias, script_path in self._ALIAS_PATTERN.findall(step_text):
            resolved = self._resolve_script_expression(script_path)
            aliases[alias] = resolved
            self.local_aliases[alias] = resolved
        return aliases

    def extract_function_usages(self, steps: List[Step]) -> List[Dict[str, object]]:
        usages = []
        for step in steps:
            for alias, function_name in self._CALL_PATTERN.findall(step.text):
                script_path = self.local_aliases.get(alias)
                if not script_path:
                    continue
                usages.append(
                    {
                        "script_path": script_path,
                        "function_name": function_name,
                        "alias": alias,
                        "line_number": step.line_number,
                    }
                )
        return usages

    def _resolve_script_expression(self, script_path: str) -> str:
        resolved = script_path.replace("\\", "/")
        if resolved.startswith("classpath:"):
            resolved = resolved.replace("classpath:", "").lstrip("/")
        for var_name, var_value in self.config.variable_patterns.items():
            resolved = resolved.replace(var_name, var_value)
        return resolved
