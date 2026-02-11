"""Tests for src.etilbudsavis — offer normalization."""

from src.etilbudsavis import _map_unit, normalize_offer


class TestMapUnit:
    def test_kilogram(self):
        assert _map_unit("kg") == "kilogram"
        assert _map_unit("Kilogram") == "kilogram"

    def test_gram(self):
        assert _map_unit("g") == "kilogram"

    def test_liter(self):
        assert _map_unit("l") == "liter"
        assert _map_unit("liter") == "liter"
        assert _map_unit("litre") == "liter"

    def test_sub_volumes(self):
        assert _map_unit("dl") == "liter"
        assert _map_unit("ml") == "liter"
        assert _map_unit("cl") == "liter"

    def test_piece(self):
        assert _map_unit("stk") == "piece"
        assert _map_unit("pk") == "piece"

    def test_none(self):
        assert _map_unit(None) is None


class TestNormalizeOffer:
    def _raw_offer(self, **overrides):
        base = {
            "id": "offer-1",
            "heading": "Kyllingfilet 400 g",
            "description": "Prior, 400 g, 124,75 pr. kg.",
            "pricing": {"price": 49.90, "pre_price": None, "currency": "NOK"},
            "quantity": {
                "unit": {"symbol": "g", "si": {"symbol": "kg", "factor": 0.001}},
                "size": {"from": 400, "to": 400},
                "pieces": {"from": 1, "to": 1},
            },
            "dealer": {
                "name": "Rema 1000",
                "logo": "https://example.com/rema.png",
                "markets": [{"slug": "REMA-1000", "country_code": "NO"}],
            },
            "branding": {"name": "Rema 1000", "logo": "https://example.com/rema.png"},
            "images": {
                "thumb": "https://example.com/thumb.jpg",
                "view": "https://example.com/view.jpg",
            },
            "catalog_id": "abc123",
            "run_from": "2026-02-01T00:00:00+01:00",
            "run_till": "2026-02-15T00:00:00+01:00",
        }
        base.update(overrides)
        return base

    def test_basic_normalization(self):
        result = normalize_offer(self._raw_offer())
        assert result is not None
        assert result["source"] == "etilbudsavis"
        assert result["source_id"] == "offer-1"
        assert result["name"] == "Kyllingfilet 400 g"
        assert result["price"] == 49.90
        assert result["base_unit"] == "kilogram"
        assert result["store"] == "Rema 1000"
        # unit_price: 49.90 / (400 * 0.001) = 124.75
        assert result["unit_price"] == 124.75
        assert result["weight"] == 400.0
        assert result["weight_unit"] == "g"

    def test_image_extracted(self):
        result = normalize_offer(self._raw_offer())
        assert result["image"] == "https://example.com/view.jpg"

    def test_url_built_from_catalog(self):
        result = normalize_offer(self._raw_offer())
        assert result["url"] is not None
        assert "etilbudsavis.no" in result["url"]
        assert "REMA-1000" in result["url"]
        assert "abc123" in result["url"]

    def test_no_price_returns_none(self):
        result = normalize_offer(self._raw_offer(pricing={"price": None}))
        assert result is None

    def test_missing_pricing_uses_top_level(self):
        offer = self._raw_offer()
        offer["pricing"] = {}
        offer["price"] = 39.90
        result = normalize_offer(offer)
        assert result is not None
        assert result["price"] == 39.90

    def test_pack_size_from_pieces(self):
        """For pcs/stk items, pack_size comes from size (count), not pieces (packs)."""
        offer = self._raw_offer(
            quantity={
                "unit": {"symbol": "pcs", "si": {"symbol": "pcs", "factor": 1}},
                "size": {"from": 12, "to": 12},
                "pieces": {"from": 1, "to": 1},
            },
        )
        result = normalize_offer(offer)
        assert result["pack_size"] == 12
        # 49.90 / 12 = 4.158...
        assert result["unit_price"] == 4.16

    def test_no_dealer_defaults_to_ukjent(self):
        offer = self._raw_offer(dealer={}, branding={})
        result = normalize_offer(offer)
        assert result["store"] == "Ukjent"

    def test_validity_dates(self):
        result = normalize_offer(self._raw_offer())
        assert result["valid_from"] == "2026-02-01T00:00:00+01:00"
        assert result["valid_until"] == "2026-02-15T00:00:00+01:00"

    def test_unit_price_from_description_fallback(self):
        """When quantity data is missing, parse unit price from description."""
        offer = self._raw_offer(
            quantity={},
            description="Solvinge, 1000 g, 169,90 pr. kg.",
        )
        result = normalize_offer(offer)
        assert result["unit_price"] == 169.90
        assert result["base_unit"] == "kilogram"

    def test_kg_unit_price(self):
        """1kg product should have unit_price = price."""
        offer = self._raw_offer(
            pricing={"price": 99.0, "pre_price": 139.0, "currency": "NOK"},
            quantity={
                "unit": {"symbol": "kg", "si": {"symbol": "kg", "factor": 1}},
                "size": {"from": 1, "to": 1},
                "pieces": {"from": 1, "to": 1},
            },
        )
        result = normalize_offer(offer)
        assert result["unit_price"] == 99.0

    def test_multi_pack_unit_price(self):
        """2x400g for 86 kr should be 107.50 kr/kg."""
        offer = self._raw_offer(
            pricing={"price": 86.0, "pre_price": None, "currency": "NOK"},
            quantity={
                "unit": {"symbol": "g", "si": {"symbol": "kg", "factor": 0.001}},
                "size": {"from": 400, "to": 400},
                "pieces": {"from": 2, "to": 2},
            },
            description="400 g Fra 107,50/kg. Før fra 65,30 pr pk.",
        )
        result = normalize_offer(offer)
        assert result is not None
        assert result["unit_price"] == 107.5
