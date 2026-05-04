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
        if norm and "." not in norm.split("/")[-1]:
            norm += ".feature"
        
        return norm
