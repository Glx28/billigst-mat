"""Tests for onlinestores module — ngdata API scraping."""

import pytest

from src.onlinestores import _url_to_facet


class TestUrlToFacet:
    def test_meny_egg_url(self):
        url = "https://meny.no/varer/meieri-egg/egg"
        result = _url_to_facet(url)
        assert result is not None
        domain, store_name, facet = result
        assert domain == "meny.no"
        assert store_name == "MENY"
        assert "Egg" in facet

    def test_spar_kylling_url(self):
        url = "https://spar.no/varer/kylling-og-fjaerkre/kylling"
        result = _url_to_facet(url)
        assert result is not None
        domain, store_name, facet = result
        assert domain == "spar.no"
        assert store_name == "SPAR"
        assert "Kylling" in facet

    def test_joker_melk_url(self):
        url = "https://joker.no/varer/meieriprodukter/melk"
        result = _url_to_facet(url)
        assert result is not None
        domain, store_name, facet = result
        assert domain == "joker.no"
        assert store_name == "JOKER"
        assert "Melk" in facet

    def test_www_prefix_stripped(self):
        url = "https://www.meny.no/varer/meieri-egg/egg"
        result = _url_to_facet(url)
        assert result is not None
        assert result[0] == "meny.no"

    def test_unknown_domain_returns_none(self):
        url = "https://oda.com/no/categories/123"
        result = _url_to_facet(url)
        assert result is None

    def test_unknown_slug_returns_none(self):
        url = "https://meny.no/varer/unknown-category"
        result = _url_to_facet(url)
        assert result is None

    def test_trailing_slash_handled(self):
        url = "https://meny.no/varer/meieri-egg/egg/"
        result = _url_to_facet(url)
        assert result is not None
        assert "Egg" in result[2]
