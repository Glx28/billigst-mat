"""Tests for db module — SQLite price history."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestInitDb:
    def test_creates_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with patch("src.db.DB_PATH", db_path):
                from src.db import init_db, _connect

                init_db()

                conn = sqlite3.connect(str(db_path))
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                table_names = {t[0] for t in tables}

                assert "price_history" in table_names
                assert "item_history" in table_names
                conn.close()


class TestRecordRun:
    def test_inserts_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with patch("src.db.DB_PATH", db_path):
                from src.db import init_db, record_run, _connect

                init_db()

                record_run(
                    group_name="egg",
                    best_price=3.5,
                    best_item="Test Egg",
                    best_store="SPAR",
                    unit_label="kr/stk",
                    top_items=[
                        {
                            "source": "kassal",
                            "source_id": "123",
                            "name": "Test Egg",
                            "normalized_unit_price": 3.5,
                            "price": 42,
                            "store": "SPAR",
                        }
                    ],
                )

                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM price_history WHERE group_name = 'egg'"
                ).fetchone()

                assert row is not None
                assert row["best_price"] == 3.5
                assert row["best_item"] == "Test Egg"
                assert row["best_store"] == "SPAR"
                conn.close()


class TestGetAllTimeBest:
    def test_returns_min_price(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with patch("src.db.DB_PATH", db_path):
                from src.db import init_db, record_run, get_all_time_best

                init_db()

                record_run("egg", 5.0, "Egg A", "SPAR", "kr/stk", [])

                with patch("src.db.date") as mock_date:
                    mock_date.today.return_value.isoformat.return_value = "2026-02-12"
                    record_run("egg", 3.5, "Egg B", "Meny", "kr/stk", [])

                result = get_all_time_best("egg")
                assert result == 3.5

    def test_returns_none_for_missing_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with patch("src.db.DB_PATH", db_path):
                from src.db import init_db, get_all_time_best

                init_db()
                result = get_all_time_best("nonexistent")
                assert result is None


class TestGetPreviousBest:
    def test_returns_previous_day_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with patch("src.db.DB_PATH", db_path):
                from src.db import init_db, _connect, get_previous_best

                init_db()

                # Insert a record for yesterday
                conn = _connect()
                conn.execute(
                    """INSERT INTO price_history
                       (group_name, run_date, best_price, best_item, best_store, unit_label)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    ("egg", "2026-01-01", 4.0, "Old Egg", "Joker", "kr/stk"),
                )
                conn.commit()
                conn.close()

                result = get_previous_best("egg")
                assert result is not None
                assert result["best_price"] == 4.0
                assert result["best_item"] == "Old Egg"


class TestGetPreviousTopIds:
    def test_returns_item_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            with patch("src.db.DB_PATH", db_path):
                from src.db import init_db, _connect, get_previous_top_ids

                init_db()

                # Insert records for yesterday
                conn = _connect()
                conn.execute(
                    """INSERT INTO item_history
                       (group_name, run_date, item_key, item_name, unit_price, price, store)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    ("egg", "2026-01-01", "kassal:123", "Egg A", 3.5, 42, "SPAR"),
                )
                conn.execute(
                    """INSERT INTO item_history
                       (group_name, run_date, item_key, item_name, unit_price, price, store)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    ("egg", "2026-01-01", "kassal:456", "Egg B", 4.0, 48, "Meny"),
                )
                conn.commit()
                conn.close()

                result = get_previous_top_ids("egg")
                assert result == {"kassal:123", "kassal:456"}
