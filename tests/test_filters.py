"""Tests for src.filters — whitelist/blacklist & dedup."""

from src.filters import deduplicate, filter_items, matches_group


# ---------------------------------------------------------------------------
# matches_group
# ---------------------------------------------------------------------------


class TestMatchesGroup:
    def _group(self, **kw):
        base = {"name": "test", "include_any": [], "exclude": []}
        base.update(kw)
        return base

    def test_no_rules_passes(self):
        item = {"name": "Kyllingfilet"}
        assert matches_group(item, self._group()) is True

    def test_include_match(self):
        item = {"name": "Kyllingfilet 500g"}
        group = self._group(include_any=["filet"])
        assert matches_group(item, group) is True

    def test_include_no_match(self):
        item = {"name": "Bacon stekt"}
        group = self._group(include_any=["filet", "bryst"])
        assert matches_group(item, group) is False

    def test_exclude_blocks(self):
        item = {"name": "Kylling pålegg"}
        group = self._group(include_any=["kylling"], exclude=["pålegg"])
        assert matches_group(item, group) is False

    def test_exclude_takes_priority(self):
        item = {"name": "Sjokolade melk"}
        group = self._group(include_any=["melk"], exclude=["sjokolade"])
        assert matches_group(item, group) is False

    def test_case_insensitive(self):
        item = {"name": "KYLLINGFILET naturell"}
        group = self._group(include_any=["kyllingfilet"])
        assert matches_group(item, group) is True

    def test_category_fallback(self):
        item = {"name": "Ukjent produkt", "category": "Fjørfe og kylling"}
        group = self._group(include_any=["kylling"])
        assert matches_group(item, group) is True

    def test_empty_name_excluded(self):
        item = {"name": ""}
        group = self._group(include_any=["kylling"])
        assert matches_group(item, group) is False

    def test_missing_name_key(self):
        item = {}
        group = self._group(include_any=["kylling"])
        assert matches_group(item, group) is False

    def test_exclude_category_blocks(self):
        item = {"name": "Kyllingfilet 110g", "category": "Pålegg > Kjøttpålegg"}
        group = self._group(
            include_any=["filet"],
            exclude_category=["kjøttpålegg"],
        )
        assert matches_group(item, group) is False

    def test_exclude_category_passes(self):
        item = {
            "name": "Kyllingfilet 400g",
            "category": "Kylling og fjærkre > Kyllingfilet",
        }
        group = self._group(
            include_any=["filet"],
            exclude_category=["kjøttpålegg"],
        )
        assert matches_group(item, group) is True


# ---------------------------------------------------------------------------
# filter_items
# ---------------------------------------------------------------------------


class TestFilterItems:
    def test_filters_correctly(self):
        items = [
            {"name": "Kyllingfilet 400g"},
            {"name": "Sjokolade kake"},
            {"name": "Kyllingbryst strimler"},
        ]
        group = {
            "name": "kylling",
            "include_any": ["filet", "bryst"],
            "exclude": ["sjokolade"],
        }
        result = filter_items(items, group)
        assert len(result) == 2
        assert all("kylling" in r["name"].lower() for r in result)

    def test_empty_list(self):
        assert filter_items([], {"name": "x", "include_any": ["a"]}) == []


# ---------------------------------------------------------------------------
# deduplicate
# ---------------------------------------------------------------------------


class TestDeduplicate:
    def test_removes_dupes_by_source_id(self):
        items = [
            {"source": "kassal", "source_id": "123", "name": "A"},
            {"source": "kassal", "source_id": "123", "name": "A copy"},
            {"source": "kassal", "source_id": "456", "name": "B"},
        ]
        result = deduplicate(items)
        assert len(result) == 2

    def test_fallback_to_ean_store(self):
        items = [
            {
                "source": "etilbudsavis",
                "source_id": None,
                "ean": "111",
                "store": "Rema",
            },
            {
                "source": "etilbudsavis",
                "source_id": None,
                "ean": "111",
                "store": "Rema",
            },
            {
                "source": "etilbudsavis",
                "source_id": None,
                "ean": "222",
                "store": "Kiwi",
            },
        ]
        result = deduplicate(items)
        assert len(result) == 2

    def test_different_sources_not_deduped(self):
        items = [
            {
                "source": "kassal",
                "source_id": "100",
                "name": "Item",
                "store": "Kiwi",
                "price": 50,
            },
            {
                "source": "etilbudsavis",
                "source_id": "100",
                "name": "Item",
                "store": "Meny",
                "price": 60,
            },
        ]
        result = deduplicate(items)
        assert len(result) == 2

    def test_empty_list(self):
        assert deduplicate([]) == []
