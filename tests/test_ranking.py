"""Tests for src.ranking — sorting, triggers, leaderboard formatting."""

import json
from pathlib import Path
from unittest.mock import patch

from src.ranking import (
    detect_triggers,
    format_leaderboard,
    rank,
)


class TestRank:
    def test_sorts_by_unit_price(self):
        items = [
            {"name": "C", "normalized_unit_price": 120},
            {"name": "A", "normalized_unit_price": 50},
            {"name": "B", "normalized_unit_price": 80},
        ]
        result = rank(items, top_n=3)
        assert [r["name"] for r in result] == ["A", "B", "C"]

    def test_top_n_limit(self):
        items = [
            {"name": f"Item{i}", "normalized_unit_price": i * 10} for i in range(10)
        ]
        result = rank(items, top_n=3)
        assert len(result) == 3

    def test_empty(self):
        assert rank([], top_n=5) == []

    def test_fewer_than_top_n(self):
        items = [{"name": "A", "normalized_unit_price": 10}]
        result = rank(items, top_n=5)
        assert len(result) == 1


class TestDetectTriggers:
    def _items(self, prices):
        return [
            {
                "name": f"Item{i}",
                "normalized_unit_price": p,
                "target_unit": "kilogram",
                "source": "kassal",
                "source_id": str(i),
                "store": "Rema",
            }
            for i, p in enumerate(prices)
        ]

    @patch("src.ranking.record_run")
    @patch("src.ranking.get_previous_top_ids", return_value=set())
    @patch("src.ranking.get_previous_best", return_value=None)
    @patch("src.ranking.get_all_time_best", return_value=None)
    def test_new_best_on_first_run(self, mock_atb, mock_pb, mock_ids, mock_rec):
        items = self._items([50, 60, 70])
        triggers = detect_triggers("test", items)
        types = [t["type"] for t in triggers]
        assert "new_best" in types

    @patch("src.ranking.record_run")
    @patch("src.ranking.get_previous_top_ids", return_value={"kassal:0"})
    @patch("src.ranking.get_previous_best", return_value={"best_price": 60})
    @patch("src.ranking.get_all_time_best", return_value=60.0)
    def test_new_best_when_cheaper(self, mock_atb, mock_pb, mock_ids, mock_rec):
        items = self._items([50, 65, 70])
        triggers = detect_triggers("test", items)
        types = [t["type"] for t in triggers]
        assert "new_best" in types

    @patch("src.ranking.record_run")
    @patch("src.ranking.get_previous_top_ids", return_value={"kassal:0"})
    @patch("src.ranking.get_previous_best", return_value={"best_price": 40})
    @patch("src.ranking.get_all_time_best", return_value=40.0)
    def test_no_new_best_when_same_or_higher(
        self, mock_atb, mock_pb, mock_ids, mock_rec
    ):
        items = self._items([50, 60])
        triggers = detect_triggers("test", items)
        types = [t["type"] for t in triggers]
        assert "new_best" not in types

    @patch("src.ranking.record_run")
    @patch("src.ranking.get_previous_top_ids", return_value={"kassal:99"})
    @patch("src.ranking.get_previous_best", return_value={"best_price": 100})
    @patch("src.ranking.get_all_time_best", return_value=40.0)
    def test_enters_top_n(self, mock_atb, mock_pb, mock_ids, mock_rec):
        items = self._items([50, 60, 70])
        triggers = detect_triggers("test", items, top_n=3)
        types = [t["type"] for t in triggers]
        # All items are new entries (99 was previous)
        assert "enters_top_n" in types

    @patch("src.ranking.record_run")
    @patch("src.ranking.get_previous_top_ids", return_value=set())
    @patch("src.ranking.get_previous_best", return_value=None)
    @patch("src.ranking.get_all_time_best", return_value=None)
    def test_below_threshold(self, mock_atb, mock_pb, mock_ids, mock_rec):
        items = self._items([80, 100, 120])
        triggers = detect_triggers("test", items, threshold=90)
        below = [t for t in triggers if t["type"] == "below_threshold"]
        assert len(below) == 1
        assert below[0]["price"] == "80.00"

    @patch("src.ranking.record_run")
    @patch("src.ranking.get_previous_top_ids", return_value=set())
    @patch("src.ranking.get_previous_best", return_value={"best_price": 100})
    @patch("src.ranking.get_all_time_best", return_value=80.0)
    def test_price_drop_trigger(self, mock_atb, mock_pb, mock_ids, mock_rec):
        items = self._items([80])  # 20% drop
        triggers = detect_triggers("test", items)
        types = [t["type"] for t in triggers]
        assert "price_drop" in types

    @patch("src.ranking.record_run")
    @patch("src.ranking.get_previous_top_ids", return_value=set())
    @patch("src.ranking.get_previous_best", return_value=None)
    @patch("src.ranking.get_all_time_best", return_value=None)
    def test_empty_items_no_triggers(self, mock_atb, mock_pb, mock_ids, mock_rec):
        assert detect_triggers("test", []) == []

    @patch("src.ranking.record_run")
    @patch("src.ranking.get_previous_top_ids", return_value=set())
    @patch("src.ranking.get_previous_best", return_value=None)
    @patch("src.ranking.get_all_time_best", return_value=None)
    def test_records_to_db(self, mock_atb, mock_pb, mock_ids, mock_rec):
        items = self._items([50])
        detect_triggers("test", items)
        mock_rec.assert_called_once()


class TestFormatLeaderboard:
    def test_formats_items(self):
        items = [
            {
                "name": "Kyllingfilet",
                "normalized_unit_price": 89.50,
                "price": 49.90,
                "target_unit": "kilogram",
                "source": "kassal",
                "store": "Rema 1000",
                "valid_until": None,
                "url": "https://example.com/product",
            },
        ]
        text = format_leaderboard("kylling", "Kylling", items)
        assert "Kylling" in text
        assert "89.50" in text
        assert "kr/kg" in text
        assert "Rema 1000" in text
        assert "https://example.com/product" in text

    def test_no_items(self):
        text = format_leaderboard("kylling", "Kylling", [])
        assert "Ingen resultater" in text

    def test_source_tag_etilbudsavis(self):
        items = [
            {
                "name": "Egg 12pk",
                "normalized_unit_price": 3.0,
                "price": 36.0,
                "target_unit": "piece",
                "source": "etilbudsavis",
                "store": "Kiwi",
                "valid_until": "2026-02-15T00:00:00",
            },
        ]
        text = format_leaderboard("egg", "Egg", items)
        assert "📰" in text
        assert "2026-02-15" in text
