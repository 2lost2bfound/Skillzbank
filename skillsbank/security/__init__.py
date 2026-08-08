"""Security hardening: input validation, sanitization, safe errors."""

from __future__ import annotations

import hashlib
import html
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ── Input Validation ─────────────────────────────────────────────────

# Valid patterns for various input types
_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
_SAFE_SEARCH_QUERY = re.compile(r"^[\w\s\-\.\*\+\"\'\(\)\|\!\@\#\%\&\=]+$")
_SAFE_PATH_COMPONENT = re.compile(r"^[a-zA-Z0-9_\-\.\/]+$")
_DANGEROUS_SQL = re.compile(
    r"(\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC|EXECUTE|UNION|TRUNCATE)\b|--|;|/\*|\*/)",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    valid: bool
    sanitized: str
    errors: list[str]

    def __bool__(self) -> bool:
        return self.valid


def validate_identifier(value: str, max_length: int = 256, field_name: str = "id") -> ValidationResult:
    """Validate a safe identifier (skill ID, repo name, etc.)."""
    errors = []
    if not value:
        return ValidationResult(False, "", [f"{field_name} is required"])

    sanitized = value.strip()
    if len(sanitized) > max_length:
        errors.append(f"{field_name} exceeds max length {max_length}")
    if not _SAFE_IDENTIFIER.match(sanitized):
        errors.append(f"{field_name} contains invalid characters")

    return ValidationResult(valid=len(errors) == 0, sanitized=sanitized, errors=errors)


def validate_search_query(query: str, max_length: int = 500) -> ValidationResult:
    """Validate and sanitize a search query."""
    errors = []
    if not query:
        return ValidationResult(False, "", ["Query is required"])

    sanitized = query.strip()
    if len(sanitized) > max_length:
        errors.append(f"Query exceeds max length {max_length}")

    # Check for SQL injection patterns
    if _DANGEROUS_SQL.search(sanitized):
        errors.append("Query contains potentially dangerous patterns")

    # Normalize unicode
    sanitized = unicodedata.normalize("NFKC", sanitized)

    return ValidationResult(valid=len(errors) == 0, sanitized=sanitized, errors=errors)


def validate_file_path(path: str, allowed_dirs: list[str] | None = None) -> ValidationResult:
    """Validate a file path against traversal attacks."""
    errors = []
    if not path:
        return ValidationResult(False, "", ["Path is required"])

    try:
        resolved = Path(path).resolve()
    except (ValueError, OSError) as e:
        return ValidationResult(False, "", [f"Invalid path: {e}"])

    # Check for path traversal
    path_str = str(resolved)
    if ".." in path:
        errors.append("Path traversal detected (..)")

    # Check allowed directories
    if allowed_dirs:
        allowed = any(path_str.startswith(str(Path(d).resolve())) for d in allowed_dirs)
        if not allowed:
            errors.append("Path not in allowed directories")

    return ValidationResult(valid=len(errors) == 0, sanitized=path_str, errors=errors)


def sanitize_html(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(text, quote=True)


def sanitize_for_fts(query: str) -> str:
    """Sanitize a query string for FTS5 (remove FTS5 special chars)."""
    # Remove FTS5 operators that could cause syntax errors
    cleaned = re.sub(r"[{}()\[\]^~]", "", query)
    # Escape quotes
    cleaned = cleaned.replace('"', '""')
    return cleaned.strip()


# ── Content Hashing ──────────────────────────────────────────────────


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def verify_content_hash(content: str, expected_hash: str) -> bool:
    """Verify content matches expected hash."""
    return secrets.compare_digest(compute_content_hash(content), expected_hash)


# ── Safe Error Messages ──────────────────────────────────────────────


class SafeError(Exception):
    """Exception that doesn't leak internal details."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.safe_message = message
        self.code = code
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.safe_message}


class ValidationError(SafeError):
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")


class NotFoundError(SafeError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(f"{resource} not found", code="NOT_FOUND")


class PermissionError(SafeError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, code="PERMISSION_DENIED")


def safe_error_response(exc: Exception) -> dict[str, str]:
    """Convert any exception to a safe error response (no internals leaked)."""
    if isinstance(exc, SafeError):
        return exc.to_dict()
    # Generic message for unexpected errors
    return {"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"}


# ── Rate Limiting (in-memory) ────────────────────────────────────────


class RateLimiter:
    """Simple in-memory rate limiter using token bucket algorithm."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed for the given key."""
        import time

        now = time.time()
        if key not in self._buckets:
            self._buckets[key] = []

        # Remove expired entries
        self._buckets[key] = [t for t in self._buckets[key] if now - t < self._window]

        if len(self._buckets[key]) >= self._max:
            return False

        self._buckets[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests for the given key."""
        import time

        now = time.time()
        if key not in self._buckets:
            return self._max
        valid = [t for t in self._buckets[key] if now - t < self._window]
        return max(0, self._max - len(valid))

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


# ── Secret Detection ─────────────────────────────────────────────────

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|credential)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})"),
    re.compile(r"(?i)(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,}"),  # GitHub tokens
    re.compile(r"(?i)(sk|pk)_(test|live)_[a-zA-Z0-9]{20,}"),  # Stripe keys
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),  # AWS access keys
]


def detect_secrets_in_content(content: str) -> list[dict[str, str]]:
    """Detect potential secrets in content."""
    findings = []
    for pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(content):
            findings.append(
                {
                    "type": "potential_secret",
                    "match_preview": match.group()[:40] + "...",
                    "position": match.start(),
                }
            )
    return findings


# ── Path Security ────────────────────────────────────────────────────


def safe_join(base: str, *parts: str) -> str:
    """Join path parts safely, preventing traversal."""
    base_path = Path(base).resolve()
    joined = base_path.joinpath(*parts).resolve()
    if not str(joined).startswith(str(base_path)):
        raise ValidationError("Path traversal detected")
    return str(joined)


def ensure_within_directory(path: str, directory: str) -> bool:
    """Check that path is within the given directory."""
    try:
        resolved = Path(path).resolve()
        dir_resolved = Path(directory).resolve()
        return str(resolved).startswith(str(dir_resolved))
    except (ValueError, OSError):
        return False


# ── DB Security ──────────────────────────────────────────────────────


def enforce_readonly_session(session) -> None:
    """Enforce read-only mode on a session (prevents writes)."""
    from sqlalchemy import event

    @event.listens_for(session, "before_flush")
    def prevent_writes(session, flush_context, instances):
        if session.new or session.dirty or session.deleted:
            raise PermissionError("Session is read-only")
