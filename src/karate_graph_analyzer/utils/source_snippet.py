import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def get_source_snippet(file_path: Optional[str], line_number: Optional[int], context_lines: int = 5) -> str:
    """Extract a snippet of source code around a line number."""
    if not file_path or line_number is None:
        return "No source location information available."
        
    if not os.path.exists(file_path):
        return f"Source file not found: {file_path}"
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)
        
        snippet = []
        for i in range(start, end):
            prefix = "> " if i == line_number - 1 else "  "
            line_content = lines[i].rstrip()
            snippet.append(f"{i+1:4d} | {prefix}{line_content}")
            
        return "\n".join(snippet)
    except Exception as e:
        logger.error(f"Error reading source snippet from {file_path}:{line_number}: {e}")
        return f"Error reading source: {str(e)}"
