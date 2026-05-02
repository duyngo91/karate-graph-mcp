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
        
        # Fallback to project root and common source dirs
        if not os.path.exists(resolved) and context.project_root:
            search_dirs = [
                context.project_root,
                os.path.join(context.project_root, "src/test/java"),
                os.path.join(context.project_root, "src/test/resources"),
            ]
            for sd in search_dirs:
                resolved_from_root = os.path.normpath(os.path.join(sd, path))
                if os.path.exists(resolved_from_root):
                    resolved = resolved_from_root
                    break
        
        return resolved

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize path for consistent node keys (cross-platform, strip prefixes)."""
        if not path:
            return ""
        
        # 1. Convert to forward slashes
        norm = path.replace("\\", "/")
        
        # 2. Strip prefixes like classpath: or file:
        if norm.startswith("classpath:/"):
            norm = norm[11:]
        elif norm.startswith("classpath:"):
            norm = norm[10:]
        elif norm.startswith("file:"):
            norm = norm[5:].lstrip("/")
        
        # 3. Handle absolute paths by looking for common root markers
        markers = [
            "src/test/java/",
            "src/test/resources/",
            "src/main/resources/",
            "features/",
        ]
        for marker in markers:
            if marker in norm:
                norm = norm.split(marker, 1)[-1]
                break

        # 4. Strip any leading slashes remaining after prefix removal
        norm = norm.lstrip("/")

        # 5. Ensure .feature extension if it's likely a feature file path
        if "." not in norm.split("/")[-1] and not norm.endswith("/") and norm:
            norm += ".feature"
        
        return norm
