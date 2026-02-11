"""URL validator for Kassal product links.

Validates kassal products by checking kassal.app for active price listings.
Products without listed prices on kassal.app are considered dead and removed.
For live products, builds store search URLs since direct product links are stale.
Also cross-checks API prices against kassal.app website prices for accuracy.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote_plus
from typing import Any

import httpx

from src.constants import EXCLUDED_KASSAL_STORES, STORE_SEARCH_URLS

logger = logging.getLogger(__name__)

# Max concurrent URL checks
_MAX_CONCURRENT = 15
_TIMEOUT = 10


def _is_excluded_store(item: dict[str, Any]) -> bool:
    """Check if the item's store is excluded from kassal results."""
    store = (item.get("store") or "").lower().strip()
    return any(store == excl or excl in store for excl in EXCLUDED_KASSAL_STORES)


def _build_search_url(item: dict[str, Any]) -> str | None:
    """Build a store search URL from the item's store name and product name."""
    store = (item.get("store") or "").lower().strip()
    name = item.get("name") or ""
    if not name:
        return None

    q = quote_plus(name)

    # Try exact store match first, then partial
    if store in STORE_SEARCH_URLS:
        return STORE_SEARCH_URLS[store].format(q=q)
    for key, tmpl in STORE_SEARCH_URLS.items():
        if key in store or store in key:
            return tmpl.format(q=q)

    # For Oda and other stores: kassal.app product page as link
    source_id = item.get("source_id")
    if source_id:
        return f"https://kassal.app/vare/{source_id}"
    return None


async def validate_urls(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate kassal items by checking kassal.app for active price listings.

    - Drops kassal items from excluded stores (Bunnpris, Coop, KIWI, REMA).
    - Checks kassal.app/vare/{id} for remaining items to verify prices exist.
    - Products with no listed prices on kassal.app are filtered out (dead).
    - Live products get store search URLs since direct product links are stale.
    - eTilbudsavis items are never touched.
    """
    result: list[dict[str, Any]] = []
    to_check: list[dict[str, Any]] = []

    for item in items:
        if item.get("source") != "kassal":
            result.append(item)
            continue

        # Drop excluded stores entirely
        if _is_excluded_store(item):
            logger.debug("Excluded store: %s (%s)", item.get("store"), item.get("name"))
            continue

        to_check.append(item)

    if not to_check:
        return result

    # Check kassal.app for active price listings
    validated = await _verify_kassal_prices(to_check)
    result.extend(validated)

    dropped = len(to_check) - len(validated)
    if dropped:
        logger.info(
            "URL validator: removed %d kassal items with no active prices", dropped
        )

    return result


async def _verify_kassal_prices(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check kassal.app product pages for active price listings.

    For each item, fetches the kassal.app product page and verifies that
    at least one store has a listed price (product is not dead).
    If the item's specific store IS listed on the page, cross-checks the
    website price against the API price and corrects it if different.
    """
    import asyncio

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

    # Regex: store logo alt text + price from the same listing block
    _STORE_PRICE_RE = re.compile(
        r'alt="([^"]+)"[^>]*class="h-10 w-10".*?'
        r"text-(?:green|rose)-600[^>]*>\s*kr\s*([\d.,]+)",
        re.DOTALL,
    )

    async def check_one(item: dict[str, Any]) -> dict[str, Any] | None:
        source_id = item.get("source_id")
        if not source_id:
            return None

        kassal_url = f"https://kassal.app/vare/{source_id}"
        item_store = (item.get("store") or "").lower().strip()

        async with semaphore:
            try:
                async with httpx.AsyncClient(
                    timeout=_TIMEOUT, follow_redirects=True
                ) as client:
                    resp = await client.get(
                        kassal_url,
                        headers={"User-Agent": "food-alert/1.0"},
                    )

                    if resp.status_code >= 400:
                        logger.debug(
                            "Dead kassal page (%d): %s",
                            resp.status_code,
                            kassal_url,
                        )
                        return None

                    text = resp.text

                    # No price listings at all → product is dead
                    if "price-product-" not in text:
                        logger.debug(
                            "No prices on kassal.app: %s (%s)",
                            item.get("name"),
                            kassal_url,
                        )
                        return None

                    # Parse store→price pairs from the page
                    store_prices: dict[str, str] = {}
                    for store_name, price_str in _STORE_PRICE_RE.findall(text):
                        store_prices[store_name.lower().strip()] = price_str

                    # If this item's store has a listed price, cross-check it
                    for listed_store, price_str in store_prices.items():
                        if (
                            listed_store == item_store
                            or listed_store in item_store
                            or item_store in listed_store
                        ):
                            try:
                                web_price = float(price_str.replace(",", ".").strip())
                                api_price = item.get("price")
                                if api_price and abs(web_price - api_price) > 0.01:
                                    logger.info(
                                        "Price correction %s @ %s: API=%.2f -> web=%.2f",
                                        item.get("name"),
                                        item.get("store"),
                                        api_price,
                                        web_price,
                                    )
                                    item["price"] = web_price
                                    item["unit_price"] = None
                            except ValueError:
                                pass
                            break

                    # Product is alive — set store search URL
                    search_url = _build_search_url(item)
                    if search_url:
                        item["url"] = search_url
                    else:
                        item["url"] = kassal_url
                    return item

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.debug(
                    "Kassal check failed: %s (%s)",
                    kassal_url,
                    type(exc).__name__,
                )
                return None
            except Exception:
                logger.debug("Kassal check error: %s", kassal_url, exc_info=True)
                return None

    results = await asyncio.gather(*(check_one(item) for item in items))
    return [r for r in results if r is not None]
