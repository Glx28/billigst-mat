"""Tests for url_validator module — Kassal URL validation."""

import pytest

from src.url_validator import _is_excluded_store, _build_search_url


class TestIsExcludedStore:
    def test_bunnpris_excluded(self):
        item = {"store": "Bunnpris", "name": "Eggs"}
        assert _is_excluded_store(item) is True

    def test_coop_excluded(self):
        item = {"store": "Coop Extra", "name": "Milk"}
        assert _is_excluded_store(item) is True

    def test_kiwi_excluded(self):
        item = {"store": "KIWI", "name": "Eggs"}
        assert _is_excluded_store(item) is True

    def test_rema_excluded(self):
        item = {"store": "Rema 1000", "name": "Bread"}
        assert _is_excluded_store(item) is True

    def test_spar_not_excluded(self):
        item = {"store": "SPAR", "name": "Eggs"}
        assert _is_excluded_store(item) is False

    def test_meny_not_excluded(self):
        item = {"store": "Meny", "name": "Chicken"}
        assert _is_excluded_store(item) is False

    def test_joker_not_excluded(self):
        item = {"store": "Joker", "name": "Fish"}
        assert _is_excluded_store(item) is False

    def test_case_insensitive(self):
        item = {"store": "BUNNPRIS", "name": "Eggs"}
        assert _is_excluded_store(item) is True

    def test_missing_store_not_excluded(self):
        item = {"name": "Eggs"}
        assert _is_excluded_store(item) is False

    def test_empty_store_not_excluded(self):
        item = {"store": "", "name": "Eggs"}
        assert _is_excluded_store(item) is False


class TestBuildSearchUrl:
    def test_spar_search_url(self):
        item = {"store": "spar", "name": "Kyllingfilet"}
        url = _build_search_url(item)
        assert url is not None
        assert "spar.no/sok" in url
        assert "Kyllingfilet" in url or "kyllingfilet" in url.lower()

    def test_meny_search_url(self):
        item = {"store": "meny", "name": "Egg 12pk"}
        url = _build_search_url(item)
        assert url is not None
        assert "meny.no/sok" in url

    def test_joker_search_url(self):
        item = {"store": "joker", "name": "Melk"}
        url = _build_search_url(item)
        assert url is not None
        assert "joker.no/sok" in url

    def test_holdbart_search_url(self):
        item = {"store": "holdbart", "name": "Laksefilet"}
        url = _build_search_url(item)
        assert url is not None
        assert "holdbart.no/search" in url

    def test_unknown_store_with_source_id(self):
        item = {"store": "unknown", "name": "Product", "source_id": "abc123"}
        url = _build_search_url(item)
        assert url is not None
        assert "kassal.app/vare/abc123" in url

    def test_unknown_store_no_source_id(self):
        item = {"store": "unknown", "name": "Product"}
        url = _build_search_url(item)
        assert url is None

    def test_missing_name_returns_none(self):
        item = {"store": "spar", "name": ""}
        url = _build_search_url(item)
        assert url is None

    def test_partial_store_match(self):
        # "Meny Storo" should match "meny" template
        item = {"store": "Meny Storo", "name": "Test"}
        url = _build_search_url(item)
        assert url is not None
        assert "meny.no/sok" in url

    def test_url_encodes_special_chars(self):
        item = {"store": "spar", "name": "Øko Egg"}
        url = _build_search_url(item)
        assert url is not None
        # URL should be encoded
        assert " " not in url.split("query=")[1].split("&")[0]
