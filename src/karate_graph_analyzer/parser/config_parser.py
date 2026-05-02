"""
Karate Config Parser

Automatically extracts variables from karate-config*.js files.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class KarateConfigParser:
    """Parser for karate-config*.js files to extract environment variables."""
    
    def __init__(self, project_root: str):
        """Initialize config parser.
        
        Args:
            project_root: Root directory of the Karate project
        """
        self.project_root = Path(project_root)
        self.config_cache: Dict[str, Dict[str, str]] = {}
    
    def find_config_files(self) -> List[Path]:
        """Find all karate-config*.js files in the project.
        
        Returns:
            List of paths to config files
        """
        config_files = []
        
        # Common locations for config files
        search_paths = [
            self.project_root / "src/test/java",
            self.project_root / "src/test/resources",
            self.project_root,
        ]
        
        for search_path in search_paths:
            if search_path.exists():
                # Find all karate-config*.js files
                for config_file in search_path.glob("**/karate-config*.js"):
                    config_files.append(config_file)
        
        logger.info(f"Found {len(config_files)} config files: {[f.name for f in config_files]}")
        return config_files
    
    def parse_config_file(self, config_path: Path) -> Dict[str, str]:
        """Parse a single karate-config*.js file to extract variables.
        
        Args:
            config_path: Path to config file
        
        Returns:
            Dictionary of variable_name -> value (flattened with dot notation for nested objects)
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            variables = {}
            
            # 1. Extract flat variables from object literals and variable declarations
            # Patterns: 
            # - 'varName' : 'value'
            # - var/let/const varName = 'value'
            patterns = [
                r"['\"](\w+)['\"]\s*:\s*['\"]([^'\"]+)['\"]",
                r"(?:var|let|const)\s+(\w+)\s*=\s*['\"]([^'\"]+)['\"]",
                r"(\w+)\s*=\s*['\"]([^'\"]+)['\"]"
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for var_name, value in matches:
                    # Nới lỏng filter: Bất kỳ biến nào có giá trị trông giống đường dẫn hoặc URL đều lấy
                    if self._is_url_or_path_variable(var_name, value):
                        variables[var_name] = value
                        logger.debug(f"Extracted: {var_name} = {value}")
            
            # 2. Extract nested objects (e.g., let services = { ... })
            nested_vars = self.parse_nested_objects(content)
            for key, value in nested_vars.items():
                variables[key] = value
                logger.debug(f"Extracted nested: {key} = {value}")
            
            logger.info(f"Parsed {config_path.name}: {len(variables)} variables")
            return variables
            
        except Exception as e:
            logger.error(f"Failed to parse {config_path}: {e}")
            return {}
    
    def _is_url_or_path_variable(self, var_name: str, value: str) -> bool:
        """Check if a variable is a URL or path variable."""
        # 1. Check value patterns (High priority)
        # Any value starting with common Karate path prefixes
        value_patterns = [
            'http://', 'https://', 'classpath:', 'file:', '/', './', '../'
        ]
        
        lower_val = value.lower()
        if any(pattern in lower_val for pattern in value_patterns):
            return True
            
        # 2. Check extension-like values
        if any(lower_val.endswith(ext) for ext in ['.json', '.feature', '.yaml', '.yml', '.js', '.csv']):
            return True

        # 3. Check variable name patterns (Fallback)
        name_patterns = [
            'url', 'path', 'endpoint', 'service', 'api', 
            'page', 'locator', 'feature', 'data', 'base', 'host'
        ]
        
        if any(pattern in var_name.lower() for pattern in name_patterns):
            return True
        
        # 4. If the variable name is all caps, it's likely a constant/config
        if var_name.isupper() and len(var_name) > 2:
            return True
            
        return False
    
    def parse_all_configs(self) -> Dict[str, str]:
        """Parse all karate-config*.js files and merge variables.
        
        Returns:
            Merged dictionary of all variables
        """
        all_variables = {}
        
        config_files = self.find_config_files()
        
        for config_file in config_files:
            variables = self.parse_config_file(config_file)
            
            # Merge with priority (later files override earlier ones)
            all_variables.update(variables)
        
        logger.info(f"Total variables extracted: {len(all_variables)}")
        return all_variables
    
    def get_base_url_mapping(self) -> Dict[str, str]:
        """Get base URL mapping for parser configuration.
        
        This is a convenience method that returns variables in the format
        expected by ParserConfig.base_url_mapping.
        
        Returns:
            Dictionary suitable for ParserConfig.base_url_mapping
        """
        return self.parse_all_configs()
    
    def parse_nested_objects(self, content: str, parent_key: str = "") -> Dict[str, str]:
        """Parse nested objects from JavaScript content recursively.
        
        Handles any level of nesting:
        - let obj = { 'key': 'value' }
        - let obj = { 'a': { 'b': 'value' } }
        - let obj = { 'a': { 'b': { 'c': 'value' } } }
        
        Args:
            content: JavaScript content
            parent_key: Parent key for nested objects (used in recursion)
        
        Returns:
            Flattened dictionary with dot notation (e.g., 'services.t24.payment')
        """
        result = {}
        
        # Remove multi-line comments first
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        
        # Remove single-line comments safely (avoiding // inside quotes)
        # We look for // that is NOT preceded by : (to allow http://)
        # but a better way is to only match // at start of line or after whitespace
        content = re.sub(r'(?m)^\s*//.*?$', '', content) # Full line comments
        content = re.sub(r'\s+//(?![/]).*?$', '', content, flags=re.MULTILINE) # End of line comments with space before
        
        # Pattern to match object declarations: let varName = {
        obj_pattern = r"let\s+(\w+)\s*=\s*\{"
        
        for match in re.finditer(obj_pattern, content):
            var_name = match.group(1)
            start_pos = match.end() - 1  # Position of opening brace
            
            # Find matching closing brace
            brace_count = 0
            i = start_pos
            while i < len(content):
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        break
                i += 1
            
            if brace_count == 0:
                # Extract object content (between { and })
                obj_content = content[start_pos + 1:i]
                
                # Build full key path
                full_key = f"{parent_key}.{var_name}" if parent_key else var_name
                
                # Parse the object content
                nested_result = self._parse_object_content(obj_content, full_key)
                result.update(nested_result)
        
        return result
    
    def _parse_object_content(self, content: str, parent_key: str) -> Dict[str, str]:
        """Parse content of a JavaScript object.
        
        Args:
            content: Object content (between { and })
            parent_key: Parent key path
        
        Returns:
            Flattened dictionary
        """
        result = {}
        
        # Track brace depth to handle nested objects
        i = 0
        while i < len(content):
            # Skip whitespace
            while i < len(content) and content[i].isspace():
                i += 1
            
            if i >= len(content):
                break
            
            # Try to match a key-value pair
            # Pattern: 'key' : 'value' or 'key' : { nested }
            key_match = re.match(r"['\"](\w+)['\"]", content[i:])
            if not key_match:
                i += 1
                continue
            
            key = key_match.group(1)
            i += key_match.end()
            
            # Skip to colon
            while i < len(content) and content[i] != ':':
                i += 1
            i += 1  # Skip colon
            
            # Skip whitespace after colon
            while i < len(content) and content[i].isspace():
                i += 1
            
            if i >= len(content):
                break
            
            # Check if value is a nested object or a string
            if content[i] == '{':
                # Nested object - find matching closing brace
                brace_count = 1
                start = i + 1
                i += 1
                
                while i < len(content) and brace_count > 0:
                    if content[i] == '{':
                        brace_count += 1
                    elif content[i] == '}':
                        brace_count -= 1
                    i += 1
                
                nested_content = content[start:i-1]
                full_key = f"{parent_key}.{key}"
                
                # Recursively parse nested object
                nested_result = self._parse_object_content(nested_content, full_key)
                result.update(nested_result)
                
            elif content[i] in ['"', "'"]:
                # String value
                quote = content[i]
                i += 1
                start = i
                
                # Find closing quote
                while i < len(content) and content[i] != quote:
                    if content[i] == '\\':
                        i += 2  # Skip escaped character
                    else:
                        i += 1
                
                value = content[start:i]
                i += 1  # Skip closing quote
                
                # Only add if it's a URL or path
                if self._is_url_or_path_variable(key, value):
                    full_key = f"{parent_key}.{key}"
                    result[full_key] = value
            
            # Skip to next comma or end
            while i < len(content) and content[i] not in [',', '}']:
                i += 1
            if i < len(content) and content[i] == ',':
                i += 1
        
        return result


def auto_detect_config(project_root: str) -> Dict[str, str]:
    """Auto-detect and parse all karate-config files in a project.
    
    This is a convenience function for quick config detection.
    
    Args:
        project_root: Root directory of the Karate project
    
    Returns:
        Dictionary of all extracted variables
    
    Example:
        >>> config = auto_detect_config("/path/to/karate-project")
        >>> print(config)
        {'t24Url': 'https://t24.com', 'demoUrl': 'https://...', ...}
    """
    parser = KarateConfigParser(project_root)
    return parser.get_base_url_mapping()
