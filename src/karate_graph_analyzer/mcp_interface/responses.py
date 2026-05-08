"""Standard MCP response builders."""

from datetime import datetime
from typing import Any, Dict


def success_response(**data: Any) -> Dict[str, Any]:
    """Build a canonical success payload."""
    return {
        "success": True,
        **data,
    }


def error_response(code: Any, category: str, message: str) -> Dict[str, Any]:
    """Build a canonical error payload."""
    return {
        "success": False,
        "error": {
            "code": str(code),
            "category": category,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        },
    }
