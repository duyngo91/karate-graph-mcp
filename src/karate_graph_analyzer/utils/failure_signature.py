"""Failure fingerprinting helpers for execution reports and AI debug tools."""

import re
from typing import Dict, Optional


def normalize_error_message(error: Optional[str]) -> str:
    """Strip volatile tokens while preserving the useful failure signal."""
    if not error:
        return ""

    normalized = str(error)
    normalized = re.sub(r"\d{2}:\d{2}:\d{2}(?:\.\d+)?", "HH:MM:SS", normalized)
    normalized = re.sub(
        r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
        "UUID",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\b\d{10,}\b", "ID", normalized)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds|seconds|secs|s)\b", "DURATION", normalized, flags=re.IGNORECASE)
    normalized = " ".join(normalized.split())
    return normalized[:500]


def extract_http_status_signal(error: Optional[str]) -> Dict[str, Optional[int]]:
    """Extract expected/actual HTTP status from common Karate assertion messages."""
    if not error:
        return {"expected": None, "actual": None}

    text = str(error).lower()
    mismatch = re.search(r"expected\s+status\s+(\d{3})\s+but\s+was\s+(\d{3})", text)
    if mismatch:
        return {"expected": int(mismatch.group(1)), "actual": int(mismatch.group(2))}

    reverse_mismatch = re.search(r"status\s+(\d{3})\s+but\s+was\s+(\d{3})", text)
    if reverse_mismatch:
        return {"expected": int(reverse_mismatch.group(1)), "actual": int(reverse_mismatch.group(2))}

    actual = re.search(r"status\s+code:\s*(\d{3})", text)
    if actual:
        return {"expected": None, "actual": int(actual.group(1))}

    return {"expected": None, "actual": None}


def classify_failure(error: Optional[str], failed_step: Optional[str] = None) -> str:
    """Return a compact category that can drive grouping and AI routing."""
    text = f"{error or ''} {failed_step or ''}".lower()
    status = extract_http_status_signal(error)
    actual = status.get("actual")

    if "timeout" in text or "timed out" in text:
        return "TIMEOUT"
    if actual == 401 or "unauthorized" in text:
        return "HTTP_401_AUTH"
    if actual == 403 or "forbidden" in text:
        return "HTTP_403_AUTHZ"
    if actual == 404 or "not found" in text:
        return "HTTP_404_NOT_FOUND"
    if actual and actual >= 500:
        return "HTTP_5XX_SERVER"
    if actual and 400 <= actual < 500:
        return "HTTP_4XX_CLIENT"
    if "expected status" in text or "status code" in text:
        return "HTTP_STATUS_MISMATCH"
    if "assert" in text or "match failed" in text or "not equal" in text:
        return "ASSERTION_MISMATCH"
    if "exception" in text or "java.lang" in text:
        return "JAVA_EXCEPTION"
    if "connection" in text:
        return "CONNECTIVITY"
    return "UNKNOWN"


def build_failure_fingerprint(error: Optional[str], failed_step: Optional[str] = None) -> str:
    """Build a reusable grouping key from category, step, and normalized error."""
    normalized_error = normalize_error_message(error)
    normalized_step = normalize_error_message(failed_step)
    category = classify_failure(error, failed_step)
    parts = [category]
    if normalized_step:
        parts.append(normalized_step)
    if normalized_error:
        parts.append(normalized_error)
    return " | ".join(parts)[:700]
