"""Sensitive-data redaction for ingested logs and attributes.

Applies conservative pattern-based redaction before log entries are persisted:
common secret material (tokens, keys, passwords) and card-like numbers are
replaced with placeholders. Redaction happens at ingestion time so raw
sensitive values are never written to the database.
"""

from __future__ import annotations

import re

# Attribute keys whose values must never be stored verbatim.
SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[-_]?key|authorization|auth|credential|"
    r"session[-_]?id|cookie|private[-_]?key|client[-_]?secret)",
    re.IGNORECASE,
)

# Bearer/JWT style tokens: "Bearer <long token>" and raw JWTs.
_BEARER_PATTERN = re.compile(
    r"(?i)\b(bearer\s+)[a-z0-9\-._~+/]{16,}=*",
)
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b",
)
# Credit card numbers: 13-19 digits with optional spaces/dashes.
_CARD_PATTERN = re.compile(
    r"\b(?:\d{4}[ -]?){3}\d{1,7}\b",
)
# AWS access key IDs and generic long hex/base64 secrets after key= style hints.
_KEY_VALUE_PATTERN = re.compile(
    r"(?i)\b((?:api[_-]?key|apikey|secret|token|password|passwd|access[_-]?key)"
    r"\s*[:=]\s*)(['\"]?)[^\s'\"]{6,}\2",
)

RedactedMarker = "[REDACTED]"


def redact_text(text: str) -> str:
    """Redact secret-looking material from a free-text log message."""
    redacted = _BEARER_PATTERN.sub(lambda m: f"{m.group(1)}{RedactedMarker}", text)
    redacted = _JWT_PATTERN.sub(RedactedMarker, redacted)
    redacted = _KEY_VALUE_PATTERN.sub(lambda m: f"{m.group(1)}{RedactedMarker}", redacted)
    redacted = _CARD_PATTERN.sub(RedactedMarker, redacted)
    return redacted


def redact_attributes(attributes: dict[str, object]) -> dict[str, object]:
    """Redact values of sensitive keys and string values inside log attributes."""
    redacted: dict[str, object] = {}
    for key, value in attributes.items():
        if SENSITIVE_KEY_PATTERN.search(key):
            redacted[key] = RedactedMarker
        elif isinstance(value, str):
            redacted[key] = redact_text(value)
        elif isinstance(value, dict):
            redacted[key] = redact_attributes(value)
        else:
            redacted[key] = value
    return redacted
