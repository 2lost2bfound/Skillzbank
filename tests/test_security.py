"""Tests for skillsbank.security — validation, sanitization, safe errors."""

from __future__ import annotations

import pytest

from skillsbank.security import (
    NotFoundError,
    PermissionError,
    RateLimiter,
    SafeError,
    ValidationError,
    compute_content_hash,
    detect_secrets_in_content,
    ensure_within_directory,
    safe_error_response,
    safe_join,
    sanitize_for_fts,
    sanitize_html,
    validate_file_path,
    validate_identifier,
    validate_search_query,
    verify_content_hash,
)

# ── Identifier Validation ────────────────────────────────────────────


class TestValidateIdentifier:
    def test_valid(self):
        r = validate_identifier("my-skill_v2.0")
        assert r.valid
        assert r.sanitized == "my-skill_v2.0"

    def test_empty(self):
        r = validate_identifier("")
        assert not r.valid
        assert "required" in r.errors[0]

    def test_too_long(self):
        r = validate_identifier("a" * 300, max_length=256)
        assert not r.valid
        assert "max length" in r.errors[0]

    def test_dangerous_chars(self):
        r = validate_identifier("skill; DROP TABLE--")
        assert not r.valid

    def test_strips_whitespace(self):
        r = validate_identifier("  my-skill  ")
        assert r.valid
        assert r.sanitized == "my-skill"


# ── Search Query Validation ──────────────────────────────────────────


class TestValidateSearchQuery:
    def test_valid(self):
        r = validate_search_query("security audit tools")
        assert r.valid

    def test_empty(self):
        r = validate_search_query("")
        assert not r.valid

    def test_sql_injection(self):
        r = validate_search_query("'; DROP TABLE skills; --")
        assert not r.valid
        assert "dangerous" in r.errors[0].lower()

    def test_too_long(self):
        r = validate_search_query("a" * 600)
        assert not r.valid

    def test_unicode_normalized(self):
        r = validate_search_query("café tools")
        assert r.valid


# ── File Path Validation ─────────────────────────────────────────────


class TestValidateFilePath:
    def test_valid(self):
        r = validate_file_path("/tmp/output.json")
        assert r.valid

    def test_traversal(self):
        r = validate_file_path("/tmp/../../../etc/passwd")
        assert not r.valid
        assert "traversal" in r.errors[0].lower()

    def test_allowed_dirs(self):
        r = validate_file_path("/tmp/safe/file.json", allowed_dirs=["/tmp/safe"])
        assert r.valid

    def test_outside_allowed_dirs(self):
        r = validate_file_path("/etc/passwd", allowed_dirs=["/tmp/safe"])
        assert not r.valid


# ── HTML Sanitization ────────────────────────────────────────────────


class TestSanitize:
    def test_html_escape(self):
        assert sanitize_html("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"

    def test_fts_sanitize(self):
        cleaned = sanitize_for_fts("test [query] {with} (parens)")
        assert "[" not in cleaned
        assert "{" not in cleaned


# ── Content Hashing ──────────────────────────────────────────────────


class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("hello")
        assert h1 == h2

    def test_different_content(self):
        assert compute_content_hash("a") != compute_content_hash("b")

    def test_verify(self):
        h = compute_content_hash("test")
        assert verify_content_hash("test", h)
        assert not verify_content_hash("wrong", h)


# ── Safe Errors ──────────────────────────────────────────────────────


class TestSafeErrors:
    def test_safe_error_to_dict(self):
        e = SafeError("Something failed", code="TEST_ERROR")
        d = e.to_dict()
        assert d["error"] == "TEST_ERROR"
        assert d["message"] == "Something failed"

    def test_validation_error(self):
        e = ValidationError("Bad input")
        assert e.code == "VALIDATION_ERROR"

    def test_not_found(self):
        e = NotFoundError("Skill", "abc-123")
        assert e.code == "NOT_FOUND"
        assert "Skill not found" == e.safe_message

    def test_permission_error(self):
        e = PermissionError()
        assert e.code == "PERMISSION_DENIED"

    def test_safe_error_response_for_safe_error(self):
        e = ValidationError("Bad input")
        r = safe_error_response(e)
        assert r["error"] == "VALIDATION_ERROR"

    def test_safe_error_response_for_generic_error(self):
        r = safe_error_response(RuntimeError("internal details"))
        assert r["error"] == "INTERNAL_ERROR"
        assert "internal details" not in r["message"]


# ── Rate Limiting ────────────────────────────────────────────────────


class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert rl.is_allowed("key1")

    def test_blocks_over_limit(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            rl.is_allowed("key1")
        assert not rl.is_allowed("key1")

    def test_different_keys(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        assert rl.is_allowed("key1")
        assert rl.is_allowed("key2")

    def test_remaining(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(3):
            rl.is_allowed("key1")
        assert rl.get_remaining("key1") == 2

    def test_reset(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.is_allowed("key1")
        assert not rl.is_allowed("key1")
        rl.reset("key1")
        assert rl.is_allowed("key1")


# ── Secret Detection ─────────────────────────────────────────────────


class TestSecretDetection:
    def test_detects_api_key(self):
        content = 'API_KEY = "EXAMPLE_API_KEY_PLACEHOLDER_NOT_REAL"'
        findings = detect_secrets_in_content(content)
        assert len(findings) > 0

    def test_detects_github_token(self):
        content = "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        findings = detect_secrets_in_content(content)
        assert len(findings) > 0

    def test_clean_content(self):
        findings = detect_secrets_in_content("This is just normal text")
        assert len(findings) == 0


# ── Path Security ────────────────────────────────────────────────────


class TestPathSecurity:
    def test_safe_join(self):
        result = safe_join("/tmp/base", "subdir", "file.txt")
        assert result.startswith("/tmp/base")

    def test_safe_join_traversal_raises(self):
        with pytest.raises(ValidationError):
            safe_join("/tmp/base", "..", "..", "etc", "passwd")

    def test_ensure_within_directory(self):
        assert ensure_within_directory("/tmp/base/file.txt", "/tmp/base")
        assert not ensure_within_directory("/etc/passwd", "/tmp/base")
