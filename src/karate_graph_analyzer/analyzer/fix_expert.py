import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import re

from karate_graph_analyzer.models import FixEntry

logger = logging.getLogger(__name__)

class FixExpert:
    """Expert system for learning from fixes and suggesting solutions."""
    
    def __init__(self, kb_path: str = "fixes_kb.json"):
        """Initialize with path to Knowledge Base file.
        
        Args:
            kb_path: Path to the JSON file storing fixes.
        """
        self.kb_path = Path(kb_path)
        self.knowledge: List[Dict[str, Any]] = self._load_kb()

    def _load_kb(self) -> List[Dict[str, Any]]:
        """Load knowledge base from file."""
        if self.kb_path.exists():
            try:
                with open(self.kb_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load fixes KB: {e}")
                return []
        return []

    def _save_kb(self):
        """Save knowledge base to file."""
        try:
            self.kb_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.kb_path, 'w', encoding='utf-8') as f:
                json.dump(self.knowledge, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save fixes KB: {e}")

    def record_fix(self, node_id: str, name: str, error_message: str, solution: str, description: str, file_path: Optional[str] = None):
        """Record a successful fix for an error.
        
        Args:
            node_id: ID of the component fixed.
            name: Human readable name of the component.
            error_message: The error message that was fixed.
            solution: The code change or steps taken (diff).
            description: Description of why it failed and how it was fixed.
            file_path: Path to the file where the fix was applied.
        """
        # Normalize error message to create a pattern (remove timestamps, IDs, etc.)
        pattern = self._normalize_error(error_message)
        
        # Check if we already have this exact fix for this node
        for entry in self.knowledge:
            if entry["node_id"] == node_id and entry["error_pattern"] == pattern:
                entry["success_count"] = entry.get("success_count", 1) + 1
                entry["timestamp"] = datetime.now().isoformat()
                entry["solution"] = solution # Update with latest solution
                entry["description"] = description
                self._save_kb()
                return

        new_entry = {
            "node_id": node_id,
            "name": name,
            "error_pattern": pattern,
            "solution": solution,
            "description": description,
            "file_path": file_path,
            "timestamp": datetime.now().isoformat(),
            "success_count": 1
        }
        self.knowledge.append(new_entry)
        self._save_kb()
        logger.info(f"Recorded new fix for {node_id} (Pattern: {pattern[:50]}...)")

    def suggest_fixes(self, node_id: str, current_error: str) -> List[Dict[str, Any]]:
        """Find historical fixes that match the current error.
        
        Args:
            node_id: ID of the failing component.
            current_error: The current error message.
            
        Returns:
            List of suggested fixes sorted by relevance/success count.
        """
        pattern = self._normalize_error(current_error)
        suggestions = []
        
        for entry in self.knowledge:
            # High relevance: Same node AND same error pattern
            if entry["node_id"] == node_id and entry["error_pattern"] == pattern:
                entry["relevance"] = "HIGH (Exact Match)"
                suggestions.append(entry)
                continue
                
            # Medium relevance: Same error pattern on DIFFERENT node of same type/name
            # Or similar error pattern
            if entry["error_pattern"] == pattern:
                entry["relevance"] = "MEDIUM (Similar Error elsewhere)"
                suggestions.append(entry)
        
        # Sort by success count descending
        suggestions.sort(key=lambda x: x.get("success_count", 1), reverse=True)
        return suggestions

    def _normalize_error(self, error: str) -> str:
        """Strip dynamic parts from error message to create a reusable pattern."""
        if not error: return ""
        
        # Remove timestamps (e.g. 15:30:22.123)
        error = re.sub(r'\d{2}:\d{2}:\d{2}(\.\d+)?', 'HH:MM:SS', error)
        
        # Remove UUIDs
        error = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', 'UUID', error)
        
        # Remove large numbers (IDs)
        error = re.sub(r'\d{10,}', 'ID', error)
        
        # Normalize whitespace
        error = ' '.join(error.split())
        
        # Take first 500 chars to avoid huge keys
        return error[:500]
