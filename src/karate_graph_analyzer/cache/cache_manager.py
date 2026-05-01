"""
Cache manager implementation.

Provides LRU caching for parsed ASTs and file change detection.
"""

import os
from collections import OrderedDict
from typing import Optional

from karate_graph_analyzer.models import FeatureAST


class CacheManager:
    """Manages LRU cache for parsed ASTs.
    
    Caches parsed ASTs keyed by (file_path, modification_timestamp).
    Implements LRU eviction when cache exceeds max_size.
    Detects file changes through timestamp comparison.
    """

    def __init__(self, max_size: int = 100) -> None:
        """Initialize cache with maximum size.

        Args:
            max_size: Maximum number of cached ASTs (default: 100)
        """
        self.max_size = max_size
        # OrderedDict maintains insertion order for LRU implementation
        # Key: file_path, Value: (modification_time, FeatureAST)
        self._cache: OrderedDict[str, tuple[float, FeatureAST]] = OrderedDict()

    def get(self, file_path: str) -> Optional[FeatureAST]:
        """Get cached AST if file hasn't changed.
        
        Checks if the file exists and compares modification timestamps.
        If the file has been modified since caching, returns None.
        On cache hit, moves the entry to the end (most recently used).

        Args:
            file_path: Path to the feature file

        Returns:
            Cached AST if file hasn't changed, None otherwise
        """
        # Check if file exists
        if not os.path.exists(file_path):
            # File doesn't exist, invalidate cache if present
            if file_path in self._cache:
                del self._cache[file_path]
            return None
        
        # Get current modification time
        try:
            current_mtime = os.path.getmtime(file_path)
        except OSError:
            # Can't get modification time, treat as cache miss
            return None
        
        # Check if file is in cache
        if file_path not in self._cache:
            return None
        
        cached_mtime, cached_ast = self._cache[file_path]
        
        # Check if file has been modified
        if current_mtime != cached_mtime:
            # File has changed, invalidate cache entry
            del self._cache[file_path]
            return None
        
        # Cache hit - move to end (most recently used)
        self._cache.move_to_end(file_path)
        return cached_ast

    def put(self, file_path: str, ast: FeatureAST) -> None:
        """Cache an AST with file's current modification time.
        
        If the cache is at max_size, evicts the least recently used entry.
        Updates the entry if file_path already exists in cache.

        Args:
            file_path: Path to the feature file
            ast: Parsed AST to cache
        """
        # Get current modification time
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            # Can't get modification time, don't cache
            return
        
        # If file already in cache, remove it (will be re-added at end)
        if file_path in self._cache:
            del self._cache[file_path]
        
        # If cache is at max size, evict least recently used (first item)
        if len(self._cache) >= self.max_size:
            # Remove first item (least recently used)
            self._cache.popitem(last=False)
        
        # Add new entry at end (most recently used)
        self._cache[file_path] = (mtime, ast)

    def invalidate(self, file_path: str) -> None:
        """Invalidate cache entry for a file.

        Args:
            file_path: Path to the feature file
        """
        if file_path in self._cache:
            del self._cache[file_path]

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size.
        
        Returns:
            Number of entries currently in cache
        """
        return len(self._cache)
    
    def contains(self, file_path: str) -> bool:
        """Check if file is in cache (without checking modification time).
        
        Args:
            file_path: Path to the feature file
            
        Returns:
            True if file is in cache, False otherwise
        """
        return file_path in self._cache
