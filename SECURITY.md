# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in SkillsBank, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email the maintainers directly or use GitHub's private vulnerability reporting feature.

## What We Consider a Vulnerability

- Injection attacks through search queries or skill content
- Path traversal in file operations
- Secret leakage in logs or error messages
- Denial of service through crafted input
- Dependency supply chain issues

## Scope

SkillsBank is a local tool that processes publicly available skill metadata from GitHub. It does not handle user authentication, payment data, or sensitive personal information.

The primary attack surface is:
- CLI input parsing
- Search query processing (FTS5)
- File import/export operations
- REST API endpoints (when running)

## Response

We aim to acknowledge reports within 48 hours and provide a fix within 7 days for confirmed vulnerabilities.
