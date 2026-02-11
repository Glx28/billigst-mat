"""eTilbudsavis (Tjek / ShopGun) API client.

Docs: https://squid-api.tjek.com/docs/
Searches offers across catalogs/flyers for Norwegian grocery stores.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from src.config import (
    ETILBUDSAVIS_API_KEY,
    GEO_LAT,
    GEO_LNG,
    GEO_RADIUS,
)
from src.constants import HOLDBART_DEALER_ID

logger = logging.getLogger(__name__)

BASE_URL = "https://squid-api.tjek.com/v2"
TIMEOUT = 20


async def fetch_holdbart_offers() -> list[dict[str, Any]]:
    """Fetch ALL current Holdbart offers from the active catalog.

    Instead of searching by term (which misses many Holdbart products with
    generic names), this fetches the active catalog and returns all offers.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # 1. Find active Holdbart catalog
        resp = await client.get(
            f"{BASE_URL}/catalogs",
            headers=_headers(),
            params={
                "r_lat": GEO_LAT,
                "r_lng": GEO_LNG,
                "r_radius": 200000,
                "dealer_ids": HOLDBART_DEALER_ID,
            },
        )
        resp.raise_for_status()
        catalogs = resp.json()

        if not catalogs:
            logger.warning("No active Holdbart catalog found")
            return []

        # Use the most recent catalog
        catalog_id = catalogs[0]["id"]
        logger.info("Holdbart catalog: %s", catalog_id)

        # 2. Fetch all offers from the catalog
        resp2 = await client.get(
            f"{BASE_URL}/offers",
            headers=_headers(),
            params={
                "catalog_ids": catalog_id,
                "r_lat": GEO_LAT,
                "r_lng": GEO_LNG,
                "r_radius": 200000,
                "limit": 100,
            },
        )
        resp2.raise_for_status()
        offers = resp2.json()
        logger.info(
            "Holdbart: fetched %d offers from catalog %s", len(offers), catalog_id
        )
        return offers


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Api-Key": ETILBUDSAVIS_API_KEY,
    }


async def search_offers(
    query: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Search eTilbudsavis for offers matching *query*.

    Returns raw offer dicts with fields like:
      heading, price, unitPrice, baseUnit, unitSizeFrom, unitSizeTo,
      validFrom, validUntil, dealer, publicId, ...
    """
    params: dict[str, Any] = {
        "query": query,
        "r_lat": GEO_LAT,
        "r_lng": GEO_LNG,
        "r_radius": GEO_RADIUS,
        "limit": limit,
        "offset": offset,
        "order_by": "-score",
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f"{BASE_URL}/offers/search",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()
        offers = resp.json()

    # Keep only currently valid offers
    now = datetime.now(timezone.utc)
    valid: list[dict[str, Any]] = []
    for o in offers:
        try:
            valid_from = datetime.fromisoformat(
                o.get("run_from", o.get("valid_from", ""))
            )
            valid_until = datetime.fromisoformat(
                o.get("run_till", o.get("valid_until", ""))
            )
            if valid_from <= now <= valid_until:
                valid.append(o)
        except (ValueError, TypeError):
            # If dates are missing/unparseable, include offer anyway
            valid.append(o)

    logger.info("eTilbudsavis '%s': %d total, %d valid", query, len(offers), len(valid))
    return valid


def normalize_offer(offer: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a raw eTilbudsavis offer into a normalized item dict.

    Returns None if price/unit info is missing.

    Normalized dict keys:
      source, source_id, name, price, unit_price, base_unit,
      store, valid_from, valid_until, url, image, pack_size, weight, weight_unit
    """
    pricing = offer.get("pricing", {}) or {}
    price = pricing.get("price") or offer.get("price")
    pre_price = pricing.get("pre_price")

    if price is None:
        return None

    # --- Quantity / weight / unit ---
    quantity = offer.get("quantity", {}) or {}
    unit_info = quantity.get("unit", {}) or {}
    unit_symbol = unit_info.get("symbol")  # e.g. "kg", "g", "l"
    si_info = unit_info.get("si", {}) or {}

    size_info = quantity.get("size", {}) or {}
    size_from = size_info.get("from")
    size_to = size_info.get("to")
    weight = size_to if size_to else size_from  # use 'to' if range
    weight_unit = unit_symbol

    # Pack size from pieces
    pieces_info = quantity.get("pieces", {}) or {}
    pack_size = pieces_info.get("from")

    # For piece-based items (pcs/stk), the size IS the pack count
    # e.g. eggs: unit=pcs, size=6 means 6 pieces, pieces=1 means 1 pack
    if unit_symbol and unit_symbol.lower() in ("pcs", "stk", "stk.") and weight:
        pack_size = int(weight)

    # --- Compute unit price from weight ---
    unit_price = None
    base_unit = _map_unit(unit_symbol)
    if price and weight and unit_symbol:
        # Convert to SI unit price (kr per kg or kr per liter)
        si_factor = si_info.get("factor", 1)
        # Multiply by number of packs if pieces > 1 (e.g. 2x400g = 800g)
        num_pieces = pieces_info.get("from") or 1
        total_weight_in_si = weight * si_factor * num_pieces
        if total_weight_in_si > 0:
            unit_price = float(price) / total_weight_in_si

    # Fallback: parse from description like "145,63 pr. kg"
    if unit_price is None:
        desc = offer.get("description") or ""
        m = re.search(
            r"([\d]+(?:[,.]\d+)?)\s*(?:pr\.?\s*kg|kr/kg)", desc, re.IGNORECASE
        )
        if m:
            unit_price = float(m.group(1).replace(",", "."))
            base_unit = "kilogram"

    # --- Dealer / store info ---
    dealer = offer.get("dealer", {}) or offer.get("branding", {}) or {}
    store_name = dealer.get("name", "Ukjent")

    # --- Image ---
    images = offer.get("images", {}) or {}
    image = images.get("view") or images.get("thumb")

    # --- Link to catalog on eTilbudsavis ---
    branding = offer.get("branding", {}) or {}
    market_slug = ""
    markets = dealer.get("markets", [])
    if markets:
        market_slug = markets[0].get("slug", "")
    catalog_id = offer.get("catalog_id", "")
    offer_id = offer.get("id", "")
    url = None
    if market_slug and catalog_id and offer_id:
        url = f"https://etilbudsavis.no/{market_slug}?publication={catalog_id}&offer={offer_id}"

    # --- Detect promotions ---
    desc_lower = (offer.get("description") or "").lower()
    heading_lower = (offer.get("heading") or "").lower()
    combined = desc_lower + " " + heading_lower
    promos: list[str] = []
    if pre_price is not None:
        promos.append(f"Før {pre_price:.0f} kr")
    if "3 for 2" in combined or "3for2" in combined:
        promos.append("3 for 2")
    if re.search(r"\b2\s+for\s+\d", combined):
        promos.append("2 for ...")
    if "spar kr" in combined or "spar fra" in combined:
        m_spar = re.search(r"spar\s+(?:kr\.?\s*|fra\s+kr\.?\s*)([\d,.]+)", combined)
        if m_spar:
            promos.append(f"Spar {m_spar.group(1)} kr")
        else:
            promos.append("Spar")
    elif re.search(r"spar\s+\d", combined):
        m_spar = re.search(r"spar\s+([\d,.]+)\s*%", combined)
        if m_spar:
            promos.append(f"Spar {m_spar.group(1)}%")
    if "medlems" in combined:
        promos.append("Medlemsrabatt")
    if re.search(r"-\d+%", combined):
        m_pct = re.search(r"-(\d+)%", combined)
        if m_pct:
            promos.append(f"-{m_pct.group(1)}%")

    return {
        "source": "etilbudsavis",
        "source_id": offer.get("id") or offer.get("publicId", ""),
        "name": offer.get("heading", offer.get("name", "")).strip(),
        "description": (offer.get("description") or "").strip(),
        "price": float(price) if price else None,
        "pre_price": float(pre_price) if pre_price else None,
        "unit_price": round(unit_price, 2) if unit_price else None,
        "base_unit": base_unit,
        "weight": float(weight) if weight else None,
        "weight_unit": weight_unit,
        "store": store_name,
        "store_logo": dealer.get("logo")
        or (branding.get("logo") if branding else None),
        "valid_from": offer.get("run_from", offer.get("valid_from")),
        "valid_until": offer.get("run_till", offer.get("valid_until")),
        "url": url,
        "image": image,
        "pack_size": pack_size,
        "promos": promos,
    }


def _map_unit(raw: str | None) -> str | None:
    """Map eTilbudsavis baseUnit strings to canonical units."""
    if not raw:
        return None
    mapping = {
        "kg": "kilogram",
        "kilogram": "kilogram",
        "g": "kilogram",  # will need weight conversion
        "l": "liter",
        "liter": "liter",
        "litre": "liter",
        "dl": "liter",
        "ml": "liter",
        "cl": "liter",
        "stk": "piece",
        "stk.": "piece",
        "pcs": "piece",
        "piece": "piece",
        "pieces": "piece",
        "pk": "piece",
        "pakke": "piece",
    }
    return mapping.get(raw.lower().strip(), raw.lower().strip())
