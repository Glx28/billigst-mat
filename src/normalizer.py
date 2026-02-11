"""Price normalizer — convert all items to a canonical kr/base_unit."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Conversion factors to canonical units
WEIGHT_TO_KG: dict[str, float] = {
    "kg": 1.0,
    "kilogram": 1.0,
    "g": 0.001,
    "gram": 0.001,
    "hg": 0.1,
}

VOLUME_TO_L: dict[str, float] = {
    "l": 1.0,
    "liter": 1.0,
    "litre": 1.0,
    "dl": 0.1,
    "cl": 0.01,
    "ml": 0.001,
}


def _canon_unit(raw: str | None) -> str | None:
    """Map raw unit to canonical form."""
    if not raw:
        return None
    r = raw.lower().strip().rstrip(".")
    if r in WEIGHT_TO_KG:
        return "kilogram"
    if r in VOLUME_TO_L:
        return "liter"
    if r in ("stk", "stk.", "pcs", "piece", "pieces", "pk", "pakke"):
        return "piece"
    return r


def compute_unit_price(item: dict[str, Any], target_unit: str) -> float | None:
    """Compute or validate the unit price for *item* in *target_unit*.

    Priority:
      1. If item already has unit_price and base_unit matches target → use it.
      2. Else try to derive from price + weight/weight_unit.
      3. For piece-based: price / pack_size.

    Returns kr per target_unit, or None if impossible to compute.
    """
    existing_up = item.get("unit_price")
    existing_bu = _canon_unit(item.get("base_unit"))

    # 1) Existing unit_price already in target unit → use directly
    if existing_up is not None and existing_bu == target_unit:
        return float(existing_up)

    price = item.get("price")
    if price is None:
        return None
    price = float(price)

    # 2) Derive from weight info (kg/l-based targets)
    weight = item.get("weight")
    weight_unit = item.get("weight_unit")
    if weight and weight_unit:
        weight = float(weight)
        wu = weight_unit.lower().strip().rstrip(".")

        if target_unit == "kilogram" and wu in WEIGHT_TO_KG:
            kg = weight * WEIGHT_TO_KG[wu]
            if kg > 0:
                return price / kg

        if target_unit == "liter" and wu in VOLUME_TO_L:
            litres = weight * VOLUME_TO_L[wu]
            if litres > 0:
                return price / litres

    # 3) Piece-based
    if target_unit == "piece":
        pack_size = item.get("pack_size")
        if pack_size and float(pack_size) > 0:
            return price / float(pack_size)
        # If no pack_size, assume 1 piece
        return price

    # 4) Existing unit_price with convertible base_unit
    if existing_up is not None and existing_bu:
        existing_up = float(existing_up)
        # Try converting between compatible units
        if target_unit == "kilogram" and existing_bu == "kilogram":
            return existing_up
        if target_unit == "liter" and existing_bu == "liter":
            return existing_up

    # 5) Fallback: try to use existing unit_price even if base_unit is unclear
    #    But ONLY if base_unit is not set (truly unknown). If base_unit is set
    #    and doesn't match the target, the unit_price is in a different measure
    #    and should NOT be used (e.g. kr/kg when target is piece).
    if existing_up is not None and existing_bu is None:
        logger.warning(
            "Using unit_price %.2f for '%s' without base_unit validation (target=%s)",
            existing_up,
            item.get("name"),
            target_unit,
        )
        return float(existing_up)

    logger.debug(
        "Cannot compute unit price for '%s' (price=%.2f, target=%s)",
        item.get("name"),
        price,
        target_unit,
    )
    return None


def enrich_items(
    items: list[dict[str, Any]],
    target_unit: str,
) -> list[dict[str, Any]]:
    """Add computed 'normalized_unit_price' and 'target_unit' to each item.

    Items where unit price cannot be determined are dropped.
    """
    enriched: list[dict[str, Any]] = []
    for item in items:
        up = compute_unit_price(item, target_unit)
        if up is not None and up > 0:
            item["normalized_unit_price"] = round(up, 2)
            item["target_unit"] = target_unit
            enriched.append(item)
        else:
            logger.debug("Dropped '%s' — no unit price", item.get("name"))
    return enriched
