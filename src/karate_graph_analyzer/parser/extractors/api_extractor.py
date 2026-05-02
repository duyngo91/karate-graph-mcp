"""
API dependency extractor.

Strategy Pattern implementation for extracting HTTP API call
dependencies from Karate step text.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from karate_graph_analyzer.interfaces import IDependencyExtractor
from karate_graph_analyzer.models import Dependency, DependencyType, ParserConfig, Step

logger = logging.getLogger(__name__)


class ApiExtractor(IDependencyExtractor):
    """Extracts API call dependencies from step text.

    Handles:
    - Explicit URL strings: url 'http://example.com/api'
    - Variable references: baseUrl + '/endpoint'
    - Path statements: path '/api/users'
    - Method markers: method GET
    - Dynamic params detection
    """

    def __init__(self, config: ParserConfig) -> None:
        self.config = config

        # Pre-compile API extraction rule patterns
        self._api_rule_patterns = [
            re.compile(rule, re.IGNORECASE) for rule in self.config.api_extraction_rules
        ]

        # Compile common patterns
        self._method_pattern = re.compile(
            r"\bmethod\s+(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b", re.IGNORECASE
        )
        self._dynamic_method_pattern = re.compile(
            r"\bmethod\s+(__arg\.\w+|\w+(?!\s*\())", re.IGNORECASE
        )
        self._var_url_pattern = re.compile(
            r"\burl\s+(['\"]([^'\"]+)['\"]\s*\+\s*)?([a-zA-Z_][a-zA-Z0-9_\.]*)\b", re.IGNORECASE
        )
        self._path_pattern = re.compile(
            r"\bpath\s+['\"]([^'\"]+)['\"]", re.IGNORECASE
        )

    def can_extract(self, step_text: str) -> bool:
        step_lower = step_text.lower()
        return any(
            keyword in step_lower
            for keyword in ["url", "path", "method"]
        )

    def extract(self, step_text: str, line_number: int) -> List[Dependency]:
        dependencies: List[Dependency] = []

        # 1. Extract HTTP Methods (METHOD_MARKER)
        for match in self._method_pattern.finditer(step_text):
            method = match.group(1).upper()
            dependencies.append(
                Dependency(
                    type=DependencyType.API,
                    target="METHOD_MARKER",
                    line_number=line_number,
                    parameters={"http_method": method}
                )
            )

        # 2. Use configured API extraction rules (URL/BaseURL)
        for pattern in self._api_rule_patterns:
            for match in pattern.finditer(step_text):
                endpoint = match.group(1)
                sanitized_endpoint = self.sanitize_url(endpoint)
                if sanitized_endpoint:
                    logical_endpoint = self.normalize_logical_url(sanitized_endpoint)
                    dependencies.append(
                        Dependency(
                            type=DependencyType.API,
                            target=logical_endpoint,
                            line_number=line_number,
                            parameters={
                                "physical_url": sanitized_endpoint if logical_endpoint != sanitized_endpoint else None
                            },
                        )
                    )

        # 3. Extract variable references (URL)
        for match in self._var_url_pattern.finditer(step_text):
            prefix_val = match.group(2)
            var_name = match.group(3)
            
            # Don't extract if it's clearly not a URL variable
            if var_name.lower() in ['path', 'method', 'request', 'response', 'headers']:
                continue
                
            resolved_url = self.config.base_url_mapping.get(var_name) or \
                           self.config.base_url_mapping.get(f"${{{var_name}}}")
            
            if resolved_url:
                full_val = resolved_url
                if prefix_val:
                    full_val = prefix_val + resolved_url
                    
                # URL resolved from trusted config mapping — bypass sanitize_url
                # (config values are already validated URLs/paths)
                logical_endpoint = self.normalize_logical_url(full_val)
                if not any(dep.target == logical_endpoint for dep in dependencies):
                    dependencies.append(
                        Dependency(
                            type=DependencyType.API,
                            target=logical_endpoint,
                            line_number=line_number,
                            parameters={
                                "resolved_from": var_name,
                                "prefix": prefix_val,
                                "physical_url": full_val if logical_endpoint != full_val else None
                            },
                        )
                    )
            else:
                # Always emit unresolved variables so they can act as root nodes
                # If we have a prefix, combine it: 'https://...' + ${var_name}
                target = f"${{{var_name}}}"
                if prefix_val:
                    target = f"{prefix_val}{target}"
                    
                if not any(dep.target == target for dep in dependencies):
                    dependencies.append(
                        Dependency(
                            type=DependencyType.API,
                            target=target,
                            line_number=line_number,
                            parameters={
                                "variable": var_name, 
                                "prefix": prefix_val,
                                "unresolved": True
                            },
                        )
                    )

        # 4. Extract path statements
        for match in self._path_pattern.finditer(step_text):
            api_path = match.group(1)
            sanitized_path = self.sanitize_url(api_path)
            if sanitized_path and not any(dep.target == sanitized_path for dep in dependencies):
                dependencies.append(
                    Dependency(
                        type=DependencyType.API,
                        target=sanitized_path,
                        line_number=line_number,
                        parameters={"path_only": True},
                    )
                )

        return dependencies

    def sanitize_url(self, url: str) -> Optional[str]:
        """Sanitize extracted URL to filter out logic, code snippets, or invalid endpoints."""
        if not url:
            return None
            
        # 1. Filter out code-like strings or multi-line snippets
        logic_keywords = [
            "var ", "let ", "const ", "if (", "karate.log(", "return ", ";", "{", "}", "\n", "\r", 
            "function", "=>", "(", ")", "||", "&&", "==", "!=", '"', "'", ",", "  "
        ]
        if any(keyword in url for keyword in logic_keywords):
            return None
            
        # 2. Filter out strings that are too long or have too many slashes/dots
        if len(url) > 200:
            return None
            
        # 3. Clean common artifacts
        url = url.strip().strip('"').strip("'")
        
        # 4. Must look like a URL or a path segment
        # Allow colon (:) for protocols (http://, https://) and port numbers
        if not re.match(r'^[a-zA-Z0-9_\-\.\/:@\$\{\}]+$', url):
            return None
            
        return url

    def normalize_logical_url(self, url: str) -> str:
        """Replace physical URLs with logical variable names if found in mapping."""
        # 1. Clean trailing slash for matching
        clean_url = url.rstrip('/')
        
        # 2. Try exact match in global reverse mapping
        if clean_url in self.config.global_reverse_mapping:
            var_name = self.config.global_reverse_mapping[clean_url]
            return f"${{{var_name}}}"
            
        # Also try with original url
        if url in self.config.global_reverse_mapping:
            var_name = self.config.global_reverse_mapping[url]
            return f"${{{var_name}}}"

        # 3. Try prefix match in global reverse mapping (sorted by length desc)
        sorted_variants = sorted(self.config.global_reverse_mapping.items(), key=lambda x: len(x[0]), reverse=True)
        for physical_url, var_name in sorted_variants:
            if not physical_url or len(physical_url) < 5: continue
            
            clean_physical = physical_url.rstrip('/')
            if clean_url == clean_physical:
                return f"${{{var_name}}}"
                
            if url.startswith(clean_physical + "/"):
                return url.replace(clean_physical, f"${{{var_name}}}")
        
        # 4. Fallback to legacy base_url_mapping
        for var_name, base_url in self.config.base_url_mapping.items():
            if not base_url or len(str(base_url)) < 5: continue
            clean_base = str(base_url).rstrip('/')
            if clean_url == clean_base:
                return f"${{{var_name}}}"
            if url.startswith(clean_base + "/"):
                return url.replace(clean_base, f"${{{var_name}}}")
        
        return url

    def extract_http_method(self, steps: List[Step]) -> Optional[str]:
        """Extract HTTP method from scenario steps."""
        for step in steps:
            # Try static method first
            match = self._method_pattern.search(step.text)
            if match:
                return match.group(1).upper()

            # Try dynamic method
            match = self._dynamic_method_pattern.search(step.text)
            if match:
                method_value = match.group(1)
                if method_value.startswith('__arg') or \
                   method_value.upper() not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                    return "DYNAMIC"
        
        return None

    def detect_dynamic_params(self, path: str) -> Tuple[str, List[str]]:
        """Detect and replace dynamic parameters in API path."""
        examples = []
        id_patterns = [
            (r'/([A-Z]+-\d+)', '/{id}'),  # PROD-001
            (r'/([a-z]+-\d+)', '/{id}'),  # prod-001
            (r'/(\d+)', '/{id}'),          # 123
            (r'/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', '/{id}'),  # UUID
        ]
        
        template = path
        for pattern, replacement in id_patterns:
            matches = re.findall(pattern, template)
            if matches:
                examples.extend(matches)
                template = re.sub(pattern, replacement, template)
        
        return template, examples
