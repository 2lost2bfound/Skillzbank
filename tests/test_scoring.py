"""Tests for Phase 7: License, Quality, and Security scoring."""

from __future__ import annotations

import pytest

from skillsbank.scoring import (
    assess_security,
    compute_quality,
    detect_license,
)


class TestLicenseDetection:
    """Test license detection from various sources."""

    def test_repo_license_mit(self):
        result = detect_license(repo_license="MIT")
        assert result.detected_type == "MIT"
        assert result.confidence == 0.95
        assert result.source == "repo_metadata"
        assert result.redistributable is True
        assert result.requires_attribution is True

    def test_repo_license_apache(self):
        result = detect_license(repo_license="Apache-2.0")
        assert result.detected_type == "Apache-2.0"
        assert result.allows_commercial is True

    def test_repo_license_gpl(self):
        result = detect_license(repo_license="GPL-3.0")
        assert result.detected_type == "GPL-3.0"
        assert result.requires_attribution is True

    def test_ecosystem_metadata_license(self):
        result = detect_license(ecosystem_metadata={"license": "MIT"})
        assert result.detected_type == "MIT"
        assert result.source == "ecosystem_metadata"

    def test_ecosystem_metadata_dict_license(self):
        result = detect_license(ecosystem_metadata={"license": {"type": "Apache-2.0"}})
        assert result.detected_type == "Apache-2.0"

    def test_content_pattern_mit(self):
        result = detect_license(summary="This project is licensed under the MIT License")
        assert result.detected_type == "MIT"
        assert result.source == "content_pattern"

    def test_content_pattern_apache(self):
        result = detect_license(summary="Licensed under Apache 2.0")
        assert result.detected_type == "Apache-2.0"

    def test_unknown_license(self):
        result = detect_license(summary="A simple code formatting skill")
        assert result.detected_type == "unknown"
        assert result.confidence == 0.0

    def test_repo_license_priority_over_content(self):
        result = detect_license(
            summary="Licensed under MIT License",
            repo_license="Apache-2.0",
        )
        assert result.detected_type == "Apache-2.0"
        assert result.source == "repo_metadata"

    def test_unknown_repo_license_ignored(self):
        result = detect_license(repo_license="unknown")
        assert result.source != "repo_metadata"


class TestQualityScoring:
    """Test quality score computation."""

    def test_empty_version(self):
        result = compute_quality({})
        assert result.overall_score >= 0.0
        assert result.overall_score <= 1.0

    def test_good_version(self):
        version = {
            "summary": "A comprehensive skill for code review with detailed documentation and examples",
            "long_description": "This skill provides automated code review capabilities..." * 3,
            "domain_primary": "code_quality",
            "input_format": "SKILL.md",
            "output_format": "review",
            "capabilities": [{"name": "code-review"}, {"name": "linting"}],
            "tags": [{"name": "python"}, {"name": "quality"}],
            "install_methods": [{"method": "pip"}],
            "declared_dependencies": {"tools": ["pylint"]},
            "inferred_dependencies": {"tools": [{"name": "git"}]},
            "ecosystem_metadata": {"stars": 500},
            "security": {"risk_level": "LOW"},
        }
        result = compute_quality(version)
        assert result.overall_score > 0.5
        assert result.documentation_score > 0.5
        assert result.metadata_completeness > 0.5

    def test_minimal_version(self):
        version = {
            "summary": "A skill",
        }
        result = compute_quality(version)
        assert result.overall_score < 0.5

    def test_all_dimensions_present(self):
        result = compute_quality({"summary": "test"})
        assert "documentation" in result.dimensions
        assert "metadata_completeness" in result.dimensions
        assert "freshness" in result.dimensions
        assert "adoption" in result.dimensions
        assert "dependency_clarity" in result.dimensions
        assert "security_posture" in result.dimensions

    def test_quality_to_dict(self):
        result = compute_quality({"summary": "test"})
        d = result.to_dict()
        assert "overall_score" in d
        assert isinstance(d["overall_score"], float)

    def test_high_adoption_with_stars(self):
        version = {"ecosystem_metadata": {"stars": 5000}}
        result = compute_quality(version)
        assert result.adoption_score == 1.0

    def test_low_adoption_no_stars(self):
        version = {"ecosystem_metadata": {}}
        result = compute_quality(version)
        assert result.adoption_score == 0.2


class TestSecurityAssessment:
    """Test security risk assessment."""

    def test_empty_content(self):
        result = assess_security({})
        assert result.risk_level == "UNKNOWN"

    def test_shell_execution_detected(self):
        version = {"summary": "Run shell commands and execute bash scripts"}
        result = assess_security(version)
        assert result.shell_execution is True
        assert "shell_execution" in result.risk_factors

    def test_network_detected(self):
        version = {"summary": "Make HTTP API calls and fetch data from URLs"}
        result = assess_security(version)
        assert result.network_access is True

    def test_browser_detected(self):
        version = {"summary": "Automate browser with Playwright for testing"}
        result = assess_security(version)
        assert result.browser_automation is True

    def test_destructive_detected(self):
        version = {"summary": "Delete files and remove directories from disk"}
        result = assess_security(version)
        assert result.destructive_potential is True
        assert result.risk_level == "HIGH"

    def test_package_install_detected(self):
        version = {"summary": "pip install packages and npm install dependencies"}
        result = assess_security(version)
        assert result.package_installation is True

    def test_low_risk_skill(self):
        version = {"summary": "A simple code formatting skill for Python files"}
        result = assess_security(version)
        assert result.risk_level == "LOW"

    def test_high_risk_multiple_flags(self):
        version = {
            "summary": "Execute shell bash commands, access filesystem and delete files, make HTTP network calls, pip install packages"
        }
        result = assess_security(version)
        assert result.risk_level == "HIGH"

    def test_security_to_dict(self):
        result = assess_security({"summary": "test"})
        d = result.to_dict()
        assert "risk_level" in d
        assert "risk_factors" in d

    def test_credential_detection(self):
        version = {"summary": "Requires API key and authentication token"}
        result = assess_security(version)
        assert len(result.credential_requirements) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
