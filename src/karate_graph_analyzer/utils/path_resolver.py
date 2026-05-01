"""
Path resolution utility for Karate Graph Analyzer.
"""

import os
import re
from karate_graph_analyzer.models import PathContext


class PathResolver:
    """Resolves relative paths and variable expressions in Karate files."""

    @staticmethod
    def resolve(path: str, context: PathContext) -> str:
        """Resolve path using context and variable patterns."""
        if not path:
            return path

        match = re.search(r"read\s*\(\s*['\"]([^'\"]+)['\"]", path, re.IGNORECASE | re.DOTALL)
        if match:
            path = match.group(1)

        # Resolve variable expressions
        for var_name, var_value in context.parser_config.variable_patterns.items():
            path = path.replace(var_name, var_value)
        
        # Absolute path pass-through
        if os.path.isabs(path):
            return path
        
        # Resolve relative to current file
        current_dir = os.path.dirname(context.current_file_path)
        resolved = os.path.normpath(os.path.join(current_dir, path))
        
        # Fallback to project root
        if not os.path.exists(resolved) and context.project_root:
            resolved_from_root = os.path.normpath(os.path.join(context.project_root, path))
            if os.path.exists(resolved_from_root):
                resolved = resolved_from_root
        
        return resolved
