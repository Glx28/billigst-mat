"""Tests for src.config — YAML loading."""

from src.config import load_groups


class TestLoadGroups:
    def test_loads_groups_from_yaml(self):
        config = load_groups()
        assert "groups" in config
        groups = config["groups"]
        assert len(groups) > 0

    def test_group_has_required_fields(self):
        config = load_groups()
        for group in config["groups"]:
            assert "name" in group
            assert "search_terms" in group
            assert "base_unit" in group

    def test_notify_section_exists(self):
        config = load_groups()
        assert "notify" in config
        assert "top_n" in config["notify"]
