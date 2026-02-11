"""SQLite price-history database.

Stores the best unit price per group on each run so triggers can compare
against *all* historical data — not just the previous single run.

Tables:
  price_history  – one row per (group, run_date) with the best price seen
  item_history   – individual items seen per run (for top-N tracking)
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.config import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "price_history.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name    TEXT    NOT NULL,
            run_date      TEXT    NOT NULL,  -- ISO date
            best_price    REAL    NOT NULL,  -- normalized unit price
            best_item     TEXT    NOT NULL,
            best_store    TEXT,
            unit_label    TEXT,
            UNIQUE(group_name, run_date)
        );

        CREATE TABLE IF NOT EXISTS item_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name    TEXT    NOT NULL,
            run_date      TEXT    NOT NULL,
            item_key      TEXT    NOT NULL,  -- source:source_id
            item_name     TEXT    NOT NULL,
            unit_price    REAL    NOT NULL,
            price         REAL,
            store         TEXT,
            UNIQUE(group_name, run_date, item_key)
        );

        CREATE INDEX IF NOT EXISTS idx_ph_group
            ON price_history(group_name);
        CREATE INDEX IF NOT EXISTS idx_ih_group
            ON item_history(group_name);
        """
    )
    conn.commit()
    conn.close()
    logger.debug("Database initialized at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def get_all_time_best(group_name: str) -> float | None:
    """Return the lowest unit price ever recorded for a group, or None."""
    conn = _connect()
    row = conn.execute(
        "SELECT MIN(best_price) AS best FROM price_history WHERE group_name = ?",
        (group_name,),
    ).fetchone()
    conn.close()
    if row and row["best"] is not None:
        return float(row["best"])
    return None


def get_previous_best(group_name: str) -> dict[str, Any] | None:
    """Return the most recent (before today) best price record for a group."""
    today = date.today().isoformat()
    conn = _connect()
    row = conn.execute(
        """SELECT best_price, best_item, best_store, run_date
           FROM price_history
           WHERE group_name = ? AND run_date < ?
           ORDER BY run_date DESC LIMIT 1""",
        (group_name, today),
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_previous_top_ids(group_name: str) -> set[str]:
    """Return the set of item_keys from the most recent previous run."""
    today = date.today().isoformat()
    conn = _connect()
    rows = conn.execute(
        """SELECT item_key FROM item_history
           WHERE group_name = ? AND run_date = (
               SELECT MAX(run_date) FROM item_history
               WHERE group_name = ? AND run_date < ?
           )""",
        (group_name, group_name, today),
    ).fetchall()
    conn.close()
    return {r["item_key"] for r in rows}


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def record_run(
    group_name: str,
    best_price: float,
    best_item: str,
    best_store: str | None,
    unit_label: str,
    top_items: list[dict[str, Any]],
) -> None:
    """Record today's results for a group."""
    today = date.today().isoformat()
    conn = _connect()

    # Upsert best price
    conn.execute(
        """INSERT INTO price_history (group_name, run_date, best_price,
               best_item, best_store, unit_label)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(group_name, run_date)
           DO UPDATE SET best_price = excluded.best_price,
                         best_item  = excluded.best_item,
                         best_store = excluded.best_store,
                         unit_label = excluded.unit_label""",
        (group_name, today, best_price, best_item, best_store, unit_label),
    )

    # Record individual items
    for item in top_items:
        item_key = f"{item.get('source', '')}:{item.get('source_id', '')}"
        conn.execute(
            """INSERT INTO item_history (group_name, run_date, item_key,
                   item_name, unit_price, price, store)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(group_name, run_date, item_key)
               DO UPDATE SET unit_price = excluded.unit_price,
                             price      = excluded.price,
                             store      = excluded.store""",
            (
                group_name,
                today,
                item_key,
                item.get("name", ""),
                item.get("normalized_unit_price", 0),
                item.get("price", 0),
                item.get("store", ""),
            ),
        )

    conn.commit()
    conn.close()
