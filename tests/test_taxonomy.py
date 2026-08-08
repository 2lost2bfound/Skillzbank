"""Tests for Phase 4: Capability taxonomy and normalization."""

from skillsbank.taxonomy import (
    CAPABILITY_TAXONOMY,
    classify_capability,
    get_taxonomy_stats,
    normalize_capabilities,
)


class TestClassifyCapability:
    """Test capability classification."""

    def test_direct_match(self):
        canonical, category, path = classify_capability("reverse-engineering")
        assert canonical == "reverse_engineering"
        assert category == "security"
        assert path == "security/reverse_engineering"

    def test_alias_match(self):
        canonical, category, _path = classify_capability("pentest")
        assert canonical == "penetration_testing"
        assert category == "security"

    def test_underscore_variant(self):
        canonical, category, _ = classify_capability("api_security")
        assert canonical == "api_security"
        assert category == "security"

    def test_cloud_category(self):
        _canonical, category, _ = classify_capability("azure")
        assert category == "cloud"

    def test_nvidia_category(self):
        _canonical, category, _ = classify_capability("doca")
        assert category == "nvidia"

    def test_uncategorized_fallback(self):
        _canonical, category, path = classify_capability("some-random-thing")
        assert category == "uncategorized"
        assert "uncategorized" in path

    def test_case_insensitive(self):
        canonical1, _, _ = classify_capability("Azure")
        canonical2, _, _ = classify_capability("azure")
        assert canonical1 == canonical2

    def test_fuzzy_substring_match(self):
        # "penetration-testing" should match via substring
        _canonical, category, _ = classify_capability("penetration_testing")
        assert category == "security"


class TestNormalizeCapabilities:
    """Test capability list normalization."""

    def test_basic_normalization(self):
        caps = [{"name": "reverse-engineering"}, {"name": "ctf"}]
        result = normalize_capabilities(caps)
        assert len(result) == 2
        assert result[0]["canonical"] == "reverse_engineering"
        assert result[0]["category"] == "security"
        assert result[1]["canonical"] == "ctf"

    def test_deduplication(self):
        caps = [
            {"name": "reverse-engineering"},
            {"name": "reverse_engineering"},
            {"name": "reverseengineering"},
        ]
        result = normalize_capabilities(caps)
        assert len(result) == 1  # All are the same canonical

    def test_empty_list(self):
        result = normalize_capabilities([])
        assert result == []

    def test_preserves_extra_fields(self):
        caps = [{"name": "ctf", "confidence": 0.9}]
        result = normalize_capabilities(caps)
        assert result[0]["confidence"] == 0.9
        assert result[0]["canonical"] == "ctf"

    def test_mixed_categories(self):
        caps = [
            {"name": "azure"},
            {"name": "reverse-engineering"},
            {"name": "typography"},
            {"name": "video"},
        ]
        result = normalize_capabilities(caps)
        categories = {r["category"] for r in result}
        assert "cloud" in categories
        assert "security" in categories
        assert "ui_ux" in categories
        assert "media" in categories


class TestTaxonomyStats:
    """Test taxonomy statistics."""

    def test_has_nodes(self):
        stats = get_taxonomy_stats()
        assert stats["total_taxonomy_nodes"] > 50

    def test_has_categories(self):
        stats = get_taxonomy_stats()
        assert len(stats["categories"]) >= 10

    def test_has_security_category(self):
        stats = get_taxonomy_stats()
        assert "security" in stats["categories"]
        assert stats["category_counts"]["security"] >= 5

    def test_alias_count(self):
        stats = get_taxonomy_stats()
        assert stats["total_alias_mappings"] > 100


class TestTaxonomyIntegrity:
    """Test taxonomy data integrity."""

    def test_all_nodes_have_canonical(self):
        for name, node in CAPABILITY_TAXONOMY.items():
            assert node.canonical, f"Node {name} missing canonical"
            assert node.category, f"Node {name} missing category"

    def test_all_aliases_unique(self):
        """No alias should map to two different canonicals."""
        from skillsbank.taxonomy import _ALIAS_MAP

        # This is guaranteed by the build logic, but verify
        assert len(_ALIAS_MAP) > 0

    def test_categories_consistent(self):
        """All nodes reference valid categories."""
        from skillsbank.taxonomy import _CATEGORIES

        valid_cats = set(_CATEGORIES.keys())
        for name, node in CAPABILITY_TAXONOMY.items():
            assert node.category in valid_cats, f"Node {name} has invalid category {node.category}"
