"""Main orchestrator — fetches, filters, ranks, notifies."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import sys
from typing import Any

from src.config import DATA_DIR, load_groups, load_store_urls
from src.db import init_db
from src.etilbudsavis import fetch_holdbart_offers, normalize_offer, search_offers
from src.filters import deduplicate, filter_items
from src.onlinestores import scrape_urls
from src.normalizer import enrich_items
from src.notify import build_email, build_email_html, send_email
from src.ranking import (
    detect_triggers,
    format_leaderboard,
    rank,
)
from src.url_validator import validate_urls

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _content_changed(
    group_data: list[dict[str, Any]],
    triggers: list[dict[str, str]],
    promo_items: list[dict[str, Any]],
) -> bool:
    """Check if current content differs from the last run."""
    preview_path = DATA_DIR / "last_run.json"
    if not preview_path.exists():
        return True  # First run, always send

    try:
        with open(preview_path, "r", encoding="utf-8") as f:
            last_run = json.load(f)
    except Exception:
        return True  # Error reading, assume changed

    # Compare #1 item per group (key indicator of change)
    last_groups = last_run.get("group_data", [])
    for i, gd in enumerate(group_data):
        if i >= len(last_groups):
            return True
        last_gd = last_groups[i]
        last_top = last_gd.get("top_items", [])
        curr_top = gd.get("top_items", [])

        if not last_top or not curr_top:
            if bool(last_top) != bool(curr_top):
                return True
            continue

        # Compare first item details
        last_item = last_top[0]
        curr_item = curr_top[0]
        if (
            last_item.get("source_id") != curr_item.get("source_id")
            or abs(
                (last_item.get("normalized_unit_price") or 0)
                - (curr_item.get("normalized_unit_price") or 0)
            )
            > 0.1
        ):
            return True

    # Compare triggers
    last_triggers = last_run.get("triggers", [])
    if len(triggers) != len(last_triggers):
        return True

    # Compare promo items (by source_id)
    last_promo_ids = {item.get("source_id") for item in last_run.get("promo_items", [])}
    curr_promo_ids = {item.get("source_id") for item in promo_items}
    if last_promo_ids != curr_promo_ids:
        return True

    return False


async def fetch_group(
    group: dict[str, Any],
    online_store_cache: list[dict[str, Any]] | None = None,
    exclude_stores: set[str] | None = None,
    only_stores: set[str] | None = None,
    holdbart_cache: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Fetch items from eTilbudsavis and online stores for a single product group.

    Args:
        group: Group config from groups.yaml.
        online_store_cache: Pre-scraped online store products (shared across groups).
        exclude_stores: Store names to skip (case-insensitive).
        only_stores: If set, only include items from these stores (case-insensitive).
        holdbart_cache: Pre-fetched Holdbart offers (all from catalog).
    """
    all_items: list[dict[str, Any]] = []
    _exclude = {s.lower() for s in (exclude_stores or set())}
    _only = {s.lower() for s in (only_stores or set())} if only_stores else None

    # --- Holdbart mode: use pre-fetched catalog offers ---
    if holdbart_cache is not None:
        for raw in holdbart_cache:
            normalized = normalize_offer(raw)
            if normalized:
                all_items.append(copy.deepcopy(normalized))
    else:
        # --- eTilbudsavis search ---
        search_terms: list[str] = group.get("search_terms", [])
        for term in search_terms:
            try:
                raw_offers = await search_offers(term, limit=50)
                for raw in raw_offers:
                    normalized = normalize_offer(raw)
                    if normalized:
                        store_lower = (normalized.get("store") or "").lower()
                        if store_lower in _exclude:
                            continue
                        if _only and store_lower not in _only:
                            continue
                        all_items.append(normalized)
            except Exception:
                logger.exception("eTilbudsavis error for '%s'", term)

    # --- Online Stores (use cached results) ---
    if online_store_cache:
        # Deep-copy each item so that per-group enrichment doesn't mutate the cache
        all_items.extend(copy.deepcopy(online_store_cache))

    logger.info(
        "Group '%s': fetched %d items (etilbudsavis + online stores)",
        group["name"],
        len(all_items),
    )
    return all_items


async def process_group(
    group: dict[str, Any],
    top_n: int = 5,
    online_store_cache: list[dict[str, Any]] | None = None,
    exclude_stores: set[str] | None = None,
    only_stores: set[str] | None = None,
    holdbart_cache: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, str]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Full pipeline for one group: fetch → filter → normalize → rank → triggers.

    Returns (leaderboard_text, triggers, top_items, promo_items).
    """
    # 1. Fetch
    raw_items = await fetch_group(
        group,
        online_store_cache=online_store_cache,
        exclude_stores=exclude_stores,
        only_stores=only_stores,
        holdbart_cache=holdbart_cache,
    )

    # 2. Filter (whitelist/blacklist)
    filtered = filter_items(raw_items, group)
    logger.info(
        "Group '%s': %d → %d after filtering",
        group["name"],
        len(raw_items),
        len(filtered),
    )

    # 2b. Validate URLs (remove items with dead links)
    filtered = await validate_urls(filtered)
    logger.info("Group '%s': %d after URL validation", group["name"], len(filtered))

    # 3. Deduplicate
    unique = deduplicate(filtered)
    logger.info(
        "Group '%s': %d → %d after dedup", group["name"], len(filtered), len(unique)
    )

    # 4. Normalize prices to base unit
    target_unit = group.get("base_unit", "kilogram")
    enriched = enrich_items(unique, target_unit)
    logger.info(
        "Group '%s': %d with computable unit price", group["name"], len(enriched)
    )

    # 5. Rank
    top_items = rank(enriched, top_n=top_n)

    # 6. Detect triggers
    threshold = group.get("threshold")
    triggers = detect_triggers(
        group["name"],
        top_items,
        threshold=threshold,
        top_n=min(top_n, 3),
    )

    # 7. Format leaderboard
    leaderboard = format_leaderboard(
        group["name"],
        group.get("display_name", group["name"]),
        top_items,
    )

    # 8. Collect items with active promotions (from ALL enriched, not just top)
    promo_items: list[dict[str, Any]] = []
    for item in enriched:
        promos = item.get("promos", [])
        if promos:
            promo_items.append(item)

    return leaderboard, triggers, top_items, promo_items


async def run(mode: str = "normal") -> None:
    """Main entry point: process all groups and send digest.

    Args:
        mode: "normal" — run everything except Holdbart.
              "holdbart" — run only Holdbart; only send email if a Holdbart
                           product is #1 in any category.
    """
    init_db()

    config = load_groups()
    groups = config.get("groups", [])
    notify_config = config.get("notify", {})
    top_n = notify_config.get("top_n", 5)

    # Determine store filtering based on mode
    exclude_stores: set[str] | None = None
    only_stores: set[str] | None = None
    if mode == "holdbart":
        only_stores = {"holdbart"}
        logger.info("Holdbart mode: only processing Holdbart offers")
    else:
        exclude_stores = {"holdbart"}
        logger.info("Normal mode: excluding Holdbart offers")

    all_leaderboards: list[str] = []
    all_triggers: list[dict[str, str]] = []
    all_promo_items: list[dict[str, Any]] = []
    seen_promo_ids: set[str] = set()

    # Results per group: (leaderboard, triggers, top_items, promos, group)
    group_results: list[
        tuple[
            str,
            list[dict[str, str]],
            list[dict[str, Any]],
            list[dict[str, Any]],
            dict[str, Any],
        ]
    ] = []

    # --- Scrape online stores ONCE (shared across all groups) ---
    # Skip online stores in holdbart mode (holdbart is eTilbudsavis only)
    online_store_cache: list[dict[str, Any]] = []
    holdbart_cache: list[dict[str, Any]] | None = None
    if mode == "holdbart":
        # Fetch ALL Holdbart offers from the active catalog
        try:
            holdbart_cache = await fetch_holdbart_offers()
        except Exception:
            logger.exception("Holdbart catalog fetch error")
            holdbart_cache = []
    else:
        store_urls = load_store_urls()
        all_store_urls: list[str] = []
        for _store, urls in store_urls.items():
            all_store_urls.extend(urls)

        if all_store_urls:
            try:
                online_store_cache = await scrape_urls(all_store_urls)
            except Exception:
                logger.exception("Online store scraping error")

    for group in groups:
        logger.info("Processing group: %s", group["name"])
        group_top_n = group.get("top_n", top_n)
        leaderboard, triggers, top_items, promo_items = await process_group(
            group,
            top_n=group_top_n,
            online_store_cache=online_store_cache,
            exclude_stores=exclude_stores,
            only_stores=only_stores,
            holdbart_cache=holdbart_cache,
        )
        group_results.append((leaderboard, triggers, top_items, promo_items, group))
        all_triggers.extend(triggers)
        for item in promo_items:
            sid = item.get("source_id", "")
            if sid and sid not in seen_promo_ids:
                seen_promo_ids.add(sid)
                all_promo_items.append(item)

    # Sort groups by cheapest #1 unit price (ascending)
    def _group_sort_key(entry: tuple) -> float:
        _lb, _trigs, top_items, _promos, _grp = entry
        if top_items:
            return top_items[0].get("normalized_unit_price", float("inf"))
        return float("inf")

    group_results.sort(key=_group_sort_key)

    # Build group_data for the HTML email
    group_data: list[dict[str, Any]] = []
    leaderboard_item_keys: set[str] = set()  # track items shown in leaderboards
    for lb, _trigs, top, _promos, grp in group_results:
        all_leaderboards.append(lb)
        group_data.append(
            {
                "display_name": grp.get("display_name", grp["name"]),
                "top_items": top,
            }
        )
        # Collect keys for all items that appear in a leaderboard table
        for item in top:
            leaderboard_item_keys.add(
                f"{item.get('source', '')}:{item.get('source_id', '')}"
            )

    # Filter promo items: remove anything already shown in a leaderboard
    unique_promo_items = [
        item
        for item in all_promo_items
        if f"{item.get('source', '')}:{item.get('source_id', '')}"
        not in leaderboard_item_keys
    ]

    # Print summary to console
    print("\n" + "=" * 60)
    for lb in all_leaderboards:
        print(lb)

    if all_triggers:
        print("🔔 Triggers:")
        for t in all_triggers:
            print(f"  • [{t['type']}] {t['message']}")
    else:
        print("✅ Ingen nye varsler.")

    # Print special offers section
    if unique_promo_items:
        print("\n🏷️  Spesialtilbud:")
        # Sort by unit_price (cheapest first)
        sorted_promos = sorted(
            unique_promo_items,
            key=lambda x: x.get("unit_price") or float("inf"),
        )
        for item in sorted_promos:
            promos = item.get("promos", [])
            promo_str = " | ".join(promos)
            up = item.get("unit_price")
            bu = item.get("base_unit", "")
            bu_short = {"kilogram": "kg", "liter": "l", "piece": "stk"}.get(bu, bu)
            price = item.get("price", 0)
            store = item.get("store", "?")
            url = item.get("url", "")
            up_str = f"{up:.2f} kr/{bu_short}" if up else "?"
            print(
                f"  • [{promo_str}] {item['name']} — {up_str} ({price:.2f} kr)"
                f" @ {store}" + (f" → {url}" if url else "")
            )

    print("=" * 60 + "\n")

    # --- Holdbart mode: only send email if a Holdbart product is #1 in any category ---
    if mode == "holdbart":
        holdbart_best = []
        for gd in group_data:
            items = gd.get("top_items", [])
            if items and (items[0].get("store") or "").lower() == "holdbart":
                holdbart_best.append(
                    f"  • {gd['display_name']}: {items[0]['name']} "
                    f"@ {items[0].get('normalized_unit_price', 0):.2f} "
                    f"kr/{_UNIT_SHORT.get(items[0].get('target_unit', ''), '?')}"
                )
        if not holdbart_best:
            logger.info("Holdbart mode: no Holdbart product is #1 — skipping email")
            print(
                "ℹ️  Holdbart: ingen produkter er billigst i noen kategori — ingen e-post sendt."
            )
            return
        logger.info(
            "Holdbart mode: found %d categories with Holdbart as #1", len(holdbart_best)
        )
        print("🏷️  Holdbart er billigst i:")
        for line in holdbart_best:
            print(line)

    # Send email
    subject, body = build_email(all_leaderboards, all_triggers)
    if mode == "holdbart":
        subject = f"🏷️ Holdbart-tilbud — {len(holdbart_best)} kategorier"
    _, body_html = build_email_html(group_data, all_triggers, unique_promo_items)

    # Check if content has changed (only for Holdbart mode - normal etilbudsavis always sends)
    should_send = True
    if mode == "holdbart":
        should_send = _content_changed(group_data, all_triggers, unique_promo_items)
        if not should_send:
            logger.info("Holdbart: content unchanged — skipping email")
            print(
                "✅ Holdbart-innhold uendret siden forrige kjøring — e-post ikke sendt."
            )

    if should_send:
        send_email(subject, body, body_html)
        if all_triggers:
            logger.info("Email sent with %d triggers", len(all_triggers))
        else:
            logger.info("Email sent (no price changes detected)")

    # Save raw data for quick email preview (preview_email.py)
    preview_data = {
        "group_data": group_data,
        "triggers": all_triggers,
        "promo_items": unique_promo_items,
    }
    preview_path = DATA_DIR / "last_run.json"
    with open(preview_path, "w", encoding="utf-8") as f:
        json.dump(preview_data, f, ensure_ascii=False, default=str)
    logger.info("Saved preview data to %s", preview_path)


def main() -> None:
    mode = "holdbart" if "--holdbart" in sys.argv else "normal"
    asyncio.run(run(mode=mode))


if __name__ == "__main__":
    main()
