"""Tests for src.normalizer — unit price computation & enrichment."""

from src.normalizer import _canon_unit, compute_unit_price, enrich_items


class TestCanonUnit:
    def test_kilogram_variants(self):
        for raw in ("kg", "kilogram", "KG", "Kilogram"):
            assert _canon_unit(raw) == "kilogram"

    def test_gram(self):
        assert _canon_unit("g") == "kilogram"
        assert _canon_unit("gram") == "kilogram"

    def test_liter_variants(self):
        for raw in ("l", "liter", "litre", "L"):
            assert _canon_unit(raw) == "liter"

    def test_volume_sub_units(self):
        assert _canon_unit("dl") == "liter"
        assert _canon_unit("cl") == "liter"
        assert _canon_unit("ml") == "liter"

    def test_piece(self):
        for raw in ("stk", "stk.", "piece", "pk", "pakke"):
            assert _canon_unit(raw) == "piece"

    def test_none(self):
        assert _canon_unit(None) is None

    def test_unknown_passthrough(self):
        assert _canon_unit("dozen") == "dozen"


class TestComputeUnitPrice:
    def _item(self, **kw):
        base = {"name": "Test", "price": 50.0}
        base.update(kw)
        return base

    def test_existing_unit_price_matching_target(self):
        item = self._item(unit_price=100.0, base_unit="kilogram")
        assert compute_unit_price(item, "kilogram") == 100.0

    def test_derive_from_weight_kg(self):
        item = self._item(price=50.0, weight=0.5, weight_unit="kg")
        result = compute_unit_price(item, "kilogram")
        assert result == 100.0  # 50 / 0.5

    def test_derive_from_weight_gram(self):
        item = self._item(price=30.0, weight=500, weight_unit="g")
        result = compute_unit_price(item, "kilogram")
        assert result == 60.0  # 30 / 0.5kg

    def test_derive_from_volume_dl(self):
        item = self._item(price=20.0, weight=5, weight_unit="dl")
        result = compute_unit_price(item, "liter")
        assert result == 40.0  # 20 / 0.5L

    def test_derive_from_volume_ml(self):
        item = self._item(price=10.0, weight=500, weight_unit="ml")
        result = compute_unit_price(item, "liter")
        assert result == 20.0  # 10 / 0.5L

    def test_piece_with_pack_size(self):
        item = self._item(price=36.0, pack_size=12)
        result = compute_unit_price(item, "piece")
        assert result == 3.0

    def test_piece_no_pack_size_defaults_to_1(self):
        item = self._item(price=25.0)
        result = compute_unit_price(item, "piece")
        assert result == 25.0

    def test_no_price_returns_none(self):
        item = {"name": "Test", "price": None}
        assert compute_unit_price(item, "kilogram") is None

    def test_weight_unit_mismatch_returns_none_or_fallback(self):
        # Weight is in kg but target is liter => no weight-based calc possible
        item = self._item(price=50.0, weight=1, weight_unit="kg")
        result = compute_unit_price(item, "liter")
        # Should be None (no volume info, no existing unit_price)
        assert result is None


class TestEnrichItems:
    def test_enriches_valid_items(self):
        items = [
            {"name": "A", "price": 50.0, "weight": 1, "weight_unit": "kg"},
            {"name": "B", "price": 30.0, "weight": 500, "weight_unit": "g"},
        ]
        result = enrich_items(items, "kilogram")
        assert len(result) == 2
        assert result[0]["normalized_unit_price"] == 50.0
        assert result[0]["target_unit"] == "kilogram"
        assert result[1]["normalized_unit_price"] == 60.0

    def test_drops_items_without_unit_price(self):
        items = [
            {"name": "A", "price": 50.0, "weight": 1, "weight_unit": "kg"},
            {"name": "B", "price": None},  # can't compute
        ]
        result = enrich_items(items, "kilogram")
        assert len(result) == 1

    def test_empty_list(self):
        assert enrich_items([], "kilogram") == []
