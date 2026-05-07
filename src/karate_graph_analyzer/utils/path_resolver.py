"""
Path resolution and normalization utility for Karate Graph Analyzer.
"""

import os
import re
from typing import Optional
from karate_graph_analyzer.models import PathContext


class PathResolver:
    """Resolves relative paths and variable expressions in Karate files."""

    @staticmethod
    def resolve(path: str, context: PathContext) -> str:
        """Resolve path using context and variable patterns."""
        if not path:
            return path

        # 1. Strip read() wrapper if present
        match = re.search(r"read\s*\(\s*['\"]([^'\"]+)['\"]", path, re.IGNORECASE | re.DOTALL)
        if match:
            path = match.group(1)

        # 2. Resolve variable expressions from config
        for var_name, var_value in context.parser_config.variable_patterns.items():
            path = path.replace(var_name, var_value)
        
        # 3. Absolute path pass-through
        if os.path.isabs(path):
            return os.path.normpath(path)

        # 4. Handle classpath: prefix
        is_classpath = False
        if path.startswith("classpath:"):
            is_classpath = True
            path = path[10:].lstrip("/")

        # 5. Resolve path
        resolved = None
        
        if is_classpath:
            # For classpath, try common source dirs first
            if context.project_root:
                search_dirs = [
                    os.path.join(context.project_root, "src/test/java"),
                    os.path.join(context.project_root, "src/test/resources"),
                    os.path.join(context.project_root, "src/main/resources"),
                    context.project_root,
                ]
                for sd in search_dirs:
                    candidate = os.path.normpath(os.path.join(sd, path))
                    if os.path.exists(candidate):
                        resolved = candidate
                        break
        else:
            # Resolve relative to current file
            current_dir = os.path.dirname(context.current_file_path)
            candidate = os.path.normpath(os.path.join(current_dir, path))
            if os.path.exists(candidate):
                resolved = candidate
            
            # Fallback to search dirs if not found relative to file
            if not resolved and context.project_root:
                search_dirs = [
                    context.project_root,
                    os.path.join(context.project_root, "src/test/java"),
                    os.path.join(context.project_root, "src/test/resources"),
                ]
                for sd in search_dirs:
                    candidate = os.path.normpath(os.path.join(sd, path))
                    if os.path.exists(candidate):
                        resolved = candidate
                        break

        return resolved if resolved else path

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize path for consistent node keys (cross-platform, strip prefixes)."""
        if not path:
            return ""
        
        # 1. Convert to forward slashes for internal consistency
        norm = path.replace("\\", "/")
        
        # 2. Strip prefixes like classpath: or file: everywhere
        norm = norm.replace("classpath:/", "").replace("classpath:", "")
        norm = norm.replace("file:/", "").replace("file:", "")
        
        # 3. Use standard markers to find the logical relative path
        # These are the roots from which Karate usually resolves logical paths
        markers = [
            "src/test/java/",
            "src/test/resources/",
            "src/main/resources/",
            "src/test/features/", # Common variation
        ]
        
        matched_marker = False
        for marker in markers:
            if marker in norm:
                norm = norm.split(marker, 1)[-1]
                matched_marker = True
                break
        
        # 4. Clean up leading slashes
        norm = norm.lstrip("/")

        # 5. Ensure .feature extension if it's likely a feature file path
        # Heuristic: must not be 'Java' and should either contain a slash or be all lowercase
        # (Java classes usually start with Uppercase and don't have slashes until resolved)
        filename = norm.split("/")[-1]
        if norm and "." not in filename:
            is_java = norm.split('.')[0] == "Java"
            if not is_java and ("/" in norm or norm[0].islower()):
                norm += ".feature"
        
        return norm
    @staticmethod
    def get_env_variants(path: str, context: PathContext) -> Dict[str, str]:
        """Get all environment-specific values for a path containing variables."""
        if not path or not context or not context.parser_config:
            return {}
            
        variants = {}
        env_mapping = context.parser_config.env_url_mapping or {} # var_name -> {env: value}
        
        # Collect all unique environments
        all_envs = set()
        for env_dict in env_mapping.values():
            all_envs.update(env_dict.keys())
            
        for env in all_envs:
            resolved = path
            replaced = False
            
            # Sort variables by length descending to avoid partial matches (e.g. 'url' vs 'baseUrl')
            sorted_vars = sorted(env_mapping.keys(), key=len, reverse=True)
            
            for var_name in sorted_vars:
                env_values = env_mapping[var_name]
                val = env_values.get(env)
                if not val:
                    continue
                
                # 1. Try to replace ${var_name} pattern
                pattern_braced = f"${{{var_name}}}"
                if pattern_braced in resolved:
                    resolved = resolved.replace(pattern_braced, val)
                    replaced = True
                
                # 2. Try to replace $var_name pattern (if applicable)
                pattern_simple = f"${var_name}"
                if pattern_simple in resolved:
                    resolved = resolved.replace(pattern_simple, val)
                    replaced = True
                    
                # 3. Only replace bare var_name if it looks like a variable placeholder 
                # (e.g. in some cases users might just use the var name)
                # But we should be careful. Let's use regex for whole word if it's not a braced pattern.
                # Heuristic: if the path starts with the var_name or it's preceded by / or .
                if not replaced:
                    # Use regex for whole word match to avoid replacing parts of other words (like 'payment' in 'PaymentServices')
                    import re
                    # Match var_name as a whole word, but allow it to be at start/end or surrounded by non-alphanumeric
                    regex_pattern = r'(?P<prefix>^|[^a-zA-Z0-9_\.])' + re.escape(var_name) + r'(?P<suffix>$|[^a-zA-Z0-9_\.])'
                    
                    def replace_func(match):
                        return match.group('prefix') + val + match.group('suffix')
                    
                    new_resolved = re.sub(regex_pattern, replace_func, resolved)
                    if new_resolved != resolved:
                        resolved = new_resolved
                        replaced = True
            
            if replaced:
                variants[env] = resolved
                
        return variants
