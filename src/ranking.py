"""Ranking / leaderboard — sort, pick top-N, detect triggers."""

from __future__ import annotations

import logging
from typing import Any

from src.db import (
    get_all_time_best,
    get_previous_best,
    get_previous_top_ids,
    record_run,
)

logger = logging.getLogger(__name__)

UNIT_LABELS = {
    "kilogram": "kr/kg",
    "liter": "kr/l",
    "piece": "kr/stk",
}


def rank(items: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, Any]]:
    """Sort items by normalized_unit_price ascending, return top N."""
    ranked = sorted(items, key=lambda x: x.get("normalized_unit_price", float("inf")))
    return ranked[:top_n]


def detect_triggers(
    group_name: str,
    top_items: list[dict[str, Any]],
    threshold: float | None = None,
    top_n: int = 3,
) -> list[dict[str, str]]:
    """Compare current top items against DB history and return trigger events.

    Uses a SQLite database to track prices over time for accurate triggers:
      - new_best:        current #1 is cheaper than ALL-TIME best for this group
      - below_threshold: an item is below the configured price threshold
      - price_drop:      price dropped >10% vs previous run's best
      - enters_top_n:    a new item entered the top N
    """
    triggers: list[dict[str, str]] = []

    if not top_items:
        return triggers

    current_best = top_items[0]
    current_best_price = current_best["normalized_unit_price"]
    unit_label = UNIT_LABELS.get(current_best.get("target_unit", ""), "kr/?")

    # Fetch history from database
    all_time_best = get_all_time_best(group_name)
    prev = get_previous_best(group_name)
    prev_best_price = prev["best_price"] if prev else None
    prev_ids = get_previous_top_ids(group_name)

    # --- new_best: only trigger if this is a new ALL-TIME low ---
    if all_time_best is None or current_best_price < all_time_best - 0.01:
        triggers.append(
            {
                "type": "new_best",
                "group": group_name,
                "message": (
                    f"Ny billigste {group_name}: {current_best['name']} "
                    f"@ {current_best_price:.2f} {unit_label} "
                    f"hos {current_best.get('store', '?')}"
                ),
                "item": current_best["name"],
                "price": f"{current_best_price:.2f}",
            }
        )

    # --- below_threshold: only fire once per item (not seen at this price before) ---
    if threshold is not None:
        for item in top_items:
            if item["normalized_unit_price"] < threshold:
                triggers.append(
                    {
                        "type": "below_threshold",
                        "group": group_name,
                        "message": (
                            f"{group_name} under terskel ({threshold:.0f} {unit_label}): "
                            f"{item['name']} @ {item['normalized_unit_price']:.2f} {unit_label} "
                            f"hos {item.get('store', '?')}"
                        ),
                        "item": item["name"],
                        "price": f"{item['normalized_unit_price']:.2f}",
                    }
                )

    # --- price_drop (>10% vs previous run) ---
    if prev_best_price and current_best_price < prev_best_price * 0.9:
        drop_pct = (1 - current_best_price / prev_best_price) * 100
        triggers.append(
            {
                "type": "price_drop",
                "group": group_name,
                "message": (
                    f"Prisfall {drop_pct:.0f}% på {group_name}: "
                    f"{current_best['name']} {prev_best_price:.2f} → "
                    f"{current_best_price:.2f} {unit_label}"
                ),
                "item": current_best["name"],
                "price": f"{current_best_price:.2f}",
            }
        )

    # --- enters_top_n ---
    current_ids = {f"{i['source']}:{i['source_id']}" for i in top_items[:top_n]}
    new_entries = current_ids - prev_ids
    for item in top_items[:top_n]:
        item_key = f"{item['source']}:{item['source_id']}"
        if item_key in new_entries and prev_ids:
            triggers.append(
                {
                    "type": "enters_top_n",
                    "group": group_name,
                    "message": (
                        f"Ny i topp-{top_n} {group_name}: {item['name']} "
                        f"@ {item['normalized_unit_price']:.2f} {unit_label} "
                        f"hos {item.get('store', '?')}"
                    ),
                    "item": item["name"],
                    "price": f"{item['normalized_unit_price']:.2f}",
                }
            )

    # Record this run's results in the database
    record_run(
        group_name=group_name,
        best_price=current_best_price,
        best_item=current_best["name"],
        best_store=current_best.get("store"),
        unit_label=unit_label,
        top_items=top_items[:top_n],
    )

    return triggers


def format_leaderboard(
    group_name: str,
    display_name: str,
    top_items: list[dict[str, Any]],
) -> str:
    """Format a human-readable leaderboard string for one group."""
    if not top_items:
        return f"{display_name}: Ingen resultater\n"

    unit_label = UNIT_LABELS.get(top_items[0].get("target_unit", ""), "kr/?")

    lines = [f"{display_name} (sortert etter {unit_label}):"]
    for i, item in enumerate(top_items, 1):
        validity = ""
        if item.get("valid_until"):
            validity = f" (gyldig til {item['valid_until'][:10]})"
        source_tag = "📰" if item["source"] == "etilbudsavis" else "🛒"
        link = ""
        if item.get("url"):
            link = f" → {item['url']}"
        alt_links = ""
        for alt_url in item.get("alt_urls", []):
            alt_links += f"\n       → {alt_url}"
        lines.append(
            f"  {i}. {source_tag} {item['name']} — "
            f"{item['normalized_unit_price']:.2f} {unit_label} "
            f"({item.get('price', '?'):.2f} kr) "
            f"@ {item.get('store', '?')}{validity}{link}{alt_links}"
        )
    lines.append("")
    return "\n".join(lines)
