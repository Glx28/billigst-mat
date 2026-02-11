"""Filtering engine — whitelist/blacklist per product group."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.constants import EXCLUDED_STORES

logger = logging.getLogger(__name__)


def _is_excluded_store(item: dict[str, Any]) -> bool:
    """Check if the item's store is globally excluded."""
    store = (item.get("store") or "").lower().strip()
    if not store:
        return False
    return any(excl in store for excl in EXCLUDED_STORES)


def matches_group(item: dict[str, Any], group: dict[str, Any]) -> bool:
    """Return True if *item* passes the include/exclude rules for *group*.

    Rules (from groups.yaml):
      include_any      – item name must contain at least one of these
      exclude          – item name must NOT contain any of these
      exclude_category – item category must NOT contain any of these
    """
    name = (item.get("name") or "").lower()
    category = (item.get("category") or "").lower() if item.get("category") else ""

    # --- Exclude filter (hard block on name) ---
    excludes: list[str] = group.get("exclude", [])
    for term in excludes:
        if term.lower() in name:
            logger.debug(
                "EXCLUDED '%s' — matched exclude term '%s'", item.get("name"), term
            )
            return False

    # --- Exclude filter (hard block on category) ---
    cat_excludes: list[str] = group.get("exclude_category", [])
    for term in cat_excludes:
        if term.lower() in category:
            logger.debug(
                "EXCLUDED '%s' — matched category exclude '%s' (cat=%s)",
                item.get("name"),
                term,
                category,
            )
            return False

    # --- Include filter (must match at least one) ---
    includes: list[str] = group.get("include_any", group.get("include", []))
    if includes:
        found = any(term.lower() in name for term in includes)
        if not found:
            # Also try category matching as fallback
            if category:
                found = any(term.lower() in category for term in includes)
            if not found:
                logger.debug(
                    "SKIPPED '%s' — no include match for group '%s'",
                    item.get("name"),
                    group.get("name"),
                )
                return False

    return True


def filter_items(
    items: list[dict[str, Any]],
    group: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return only items that pass the group's include/exclude rules.

    Also drops items from globally excluded stores.
    """
    return [
        item
        for item in items
        if not _is_excluded_store(item) and matches_group(item, group)
    ]


def _strip_weight(name: str) -> str:
    """Strip weight/volume suffixes for fuzzy dedup.

    E.g. 'coop kyllingfilet 1000g' → 'coop kyllingfilet'
         'xtra kokt skinke 250g'   → 'xtra kokt skinke'
    """
    # Remove trailing weight like "1000g", "750 ml", "1,5l", "4x125g"
    stripped = re.sub(
        r"\s*\d+[x×]?\d*(?:[.,]\d+)?\s*(?:kg|g|l|dl|ml|cl|pk|stk)\b.*$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    return stripped or name


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate items.

    Dedup keys (in priority order):
      1. source + source_id  (within same source)
      2. normalized_name + store  (cross-source, e.g. same product from
         both eTilbudsavis and kassal at same store)

    Then, cross-store dedup for kassal items:
      - Same product (EAN or name) at multiple stores → keep cheapest.
      - If same price, merge store names (e.g. "SPAR / Meny").
    """
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []

    for item in items:
        # Primary key: source+source_id
        key = f"{item.get('source')}:{item.get('source_id')}"
        if not item.get("source_id"):
            # Fallback to ean+store
            key = f"{item.get('ean', '')}:{item.get('store', '')}"

        if key in seen:
            continue
        seen.add(key)

        # Cross-source dedup: normalize name + store
        raw_name = (item.get("name") or "").lower().strip()
        store = (item.get("store") or "").lower().strip()
        price = item.get("price", 0)
        cross_key = f"x:{raw_name}:{store}:{price}"
        if cross_key in seen:
            continue
        seen.add(cross_key)

        # Cross-source dedup: stripped name (no weight suffix) + store + price
        # Catches "COOP KYLLINGFILET" vs "Coop Kyllingfilet 1000g"
        stripped = _strip_weight(raw_name)
        cross_key2 = f"xs:{stripped}:{store}:{price}"
        if cross_key2 in seen:
            continue
        seen.add(cross_key2)

        unique.append(item)

    # Cross-store dedup: same product at different stores → merge or keep cheapest
    return _dedup_cross_store(unique)


def _product_key(item: dict[str, Any]) -> str:
    """Build a product identity key for cross-store dedup.

    Uses EAN if available, otherwise falls back to normalized name.
    """
    ean = item.get("ean")
    if ean:
        return f"ean:{ean}"
    return f"name:{(item.get('name') or '').lower().strip()}"


def _dedup_cross_store(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge items that are the same product across stores.

    Applies to onlinestore, coop, and kassal sources.
    eTilbudsavis items are never touched (they have unique catalog offers).

    - Same product & same price → merge into one entry with combined store name.
    - Same product & different prices → keep only the cheapest.
    """
    from collections import defaultdict

    MERGEABLE_SOURCES = {"onlinestore", "kassal", "coop"}

    # Separate mergeable and non-mergeable items
    keep_items: list[dict[str, Any]] = []
    merge_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in items:
        if item.get("source") not in MERGEABLE_SOURCES:
            keep_items.append(item)
        else:
            pkey = _product_key(item)
            merge_groups[pkey].append(item)

    # Process each product group
    deduped: list[dict[str, Any]] = []
    for pkey, group in merge_groups.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue

        # Sort by unit_price (or price) ascending
        group.sort(
            key=lambda x: x.get("normalized_unit_price")
            or x.get("unit_price")
            or x.get("price")
            or float("inf")
        )
        best_price = (
            group[0].get("normalized_unit_price")
            or group[0].get("unit_price")
            or group[0].get("price")
            or 0
        )

        # Collect all stores at the best price (within 0.1 tolerance)
        best_items = [
            it
            for it in group
            if abs(
                (
                    it.get("normalized_unit_price")
                    or it.get("unit_price")
                    or it.get("price")
                    or 0
                )
                - best_price
            )
            < 0.1
        ]

        if len(best_items) == 1:
            deduped.append(best_items[0])
        else:
            # Same price at multiple stores — merge store names
            winner = best_items[0].copy()
            store_names = []
            urls = []
            for it in best_items:
                s = it.get("store", "?")
                if s not in store_names:
                    store_names.append(s)
                if it.get("url"):
                    urls.append(it["url"])
            winner["store"] = " / ".join(store_names)
            if urls:
                winner["url"] = urls[0]
                winner["alt_urls"] = urls[1:]
            deduped.append(winner)

        dropped = len(group) - 1
        if dropped:
            logger.debug(
                "Cross-store dedup: kept %s @ %s (dropped %d)",
                group[0].get("name"),
                deduped[-1].get("store"),
                dropped,
            )

    # Reconstruct list preserving original relative order
    result: list[dict[str, Any]] = []
    merge_id_set = {id(it) for grp in merge_groups.values() for it in grp}
    first_ids = {id(grp[0]) for grp in merge_groups.values()}
    deduped_iter = iter(deduped)

    for item in items:
        if id(item) not in merge_id_set:
            result.append(item)
        elif id(item) in first_ids:
            try:
                result.append(next(deduped_iter))
            except StopIteration:
                pass

    # Append any remaining items not yet placed
    placed = {id(r) for r in result}
    for item in deduped:
        if id(item) not in placed:
            result.append(item)

    return result
