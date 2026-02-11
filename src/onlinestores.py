"""Online grocery store scrapers using discovered APIs and DOM scraping.

Supported stores:
- Meny (via ngdata API, store_id=1300)
- Spar (via ngdata API, store_id=1210)
- Joker (via ngdata API, store_id=1220)
- Oda (via Playwright DOM scraping)

URLs from config/online_store_links.txt are parsed to determine which categories
to fetch from each store's API.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

from src.constants import NGDATA_STORES

logger = logging.getLogger(__name__)

DELAY_MIN = 0.5
DELAY_MAX = 1.5
TIMEOUT = 30.0

# ============================================================================
# NGDATA category mapping
# ============================================================================

# URL slug (last path segment) → facet string, per store.
# Built from each store's /api/categories endpoint.
# The slug is the last meaningful segment in the URL path, e.g.
#   meny.no/varer/meieri-egg/egg       → slug = "egg"
#   spar.no/varer/kjott/svinekjott     → slug = "svinekjott"
#   meny.no/varer/kylling-og-fjaerkre  → slug = "kylling-og-fjaerkre" (top-level category)

_MENY_SLUG_MAP: dict[str, str] = {
    "egg": "Categories:Meieri & egg;ShoppingListGroups:Egg",
    "melk": "Categories:Meieri & egg;ShoppingListGroups:Melk",
    "helmelk": "Categories:Meieri & egg;ShoppingListGroups:Melk",
    "lettmelk": "Categories:Meieri & egg;ShoppingListGroups:Melk",
    "kylling": "Categories:Kylling og fjærkre;ShoppingListGroups:Kylling",
    "kyllingfilet": "Categories:Kylling og fjærkre;ShoppingListGroups:Kylling",
    "kyllinglar": "Categories:Kylling og fjærkre;ShoppingListGroups:Kylling",
    "kylling-og-fjaerkre": "Categories:Kylling og fjærkre",
    "kjottdeig-og-farse": "Categories:Kjøtt;ShoppingListGroups:Kjøttdeig og farse",
    "svinekjott": "Categories:Kjøtt;ShoppingListGroups:Svinekjøtt",
    "fisk": "Categories:Fisk & skalldyr;ShoppingListGroups:Fisk",
    "laks": "Categories:Fisk & skalldyr;ShoppingListGroups:Fisk",
}

_SPAR_SLUG_MAP: dict[str, str] = {
    "egg": "Categories:Meieri og egg;ShoppingListGroups:Egg",
    "melk": "Categories:Meieri og egg;ShoppingListGroups:Melk",
    "kylling-og-fjaerkre": "Categories:Kylling og fjærkre",
    "kylling": "Categories:Kylling og fjærkre;ShoppingListGroups:Kylling",
    "kjottdeig-og-farse": "Categories:Kjøtt;ShoppingListGroups:Kjøttdeig og farse",
    "svinekjott": "Categories:Kjøtt;ShoppingListGroups:Svinekjøtt",
    "fisk": "Categories:Fisk og skalldyr;ShoppingListGroups:Fisk",
}

_JOKER_SLUG_MAP: dict[str, str] = {
    "egg": "Categories:Meieriprodukter;ShoppingListGroups:Egg",
    "melk": "Categories:Meieriprodukter;ShoppingListGroups:Melk",
    "kylling-og-fjaerkre": "Categories:Kylling og fjærkre",
    "kylling": "Categories:Kylling og fjærkre;ShoppingListGroups:Kylling",
    "kjottdeig-og-farse": "Categories:Kjøtt;ShoppingListGroups:Kjøttdeig og farse",
    "svinekjott": "Categories:Kjøtt;ShoppingListGroups:Svinekjøtt",
    "fisk": "Categories:Fisk/Skalldyr;ShoppingListGroups:Fisk",
}

SLUG_MAPS: dict[str, dict[str, str]] = {
    "meny.no": _MENY_SLUG_MAP,
    "spar.no": _SPAR_SLUG_MAP,
    "joker.no": _JOKER_SLUG_MAP,
}


def _url_to_facet(url: str) -> tuple[str, str, str] | None:
    """Parse a store URL into (domain, store_display_name, facet_string).

    Returns None if the URL can't be mapped to a known facet.
    """
    parsed = urlparse(url)
    domain = parsed.hostname or ""
    if domain.startswith("www."):
        domain = domain[4:]

    if domain not in NGDATA_STORES:
        return None

    slug_map = SLUG_MAPS.get(domain, {})
    store_name = domain.split(".")[0].upper()

    # Extract path segments after /varer/
    path = parsed.path.rstrip("/")
    segments = path.split("/")

    # Try slugs from most specific (last) to least specific
    for seg in reversed(segments):
        if seg and seg != "varer":
            facet = slug_map.get(seg)
            if facet:
                return domain, store_name, facet

    return None


# ============================================================================
# NGDATA API scraper
# ============================================================================


async def _scrape_ngdata(
    store_id: str,
    product_id: str,
    store_name: str,
    facet: str,
) -> list[dict[str, Any]]:
    """Fetch products from the ngdata API for one category facet."""
    await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    url = f"https://platform-rest-prod.ngdata.no/api/products/{store_id}/{product_id}"
    params = {
        "page": 1,
        "page_size": 100,
        "full_response": "true",
        "fieldset": "maximal",
        "facets": "Category,Allergen",
        "facet": facet,
        "showNotForSale": "false",
    }

    products: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            for hit in data.get("hits", {}).get("hits", []):
                source = hit.get("_source", {})

                title = source.get("title", "")
                subtitle = source.get("subtitle", "")
                if title and subtitle:
                    name = f"{title} - {subtitle}"
                elif subtitle:
                    name = subtitle
                elif title:
                    name = title
                else:
                    name = source.get("brand", "Unknown")

                price = source.get("pricePerUnit")
                if not price:
                    continue

                # --- Price correction using comparePricePerUnit ---
                compare_price = source.get("comparePricePerUnit")
                compare_unit = (source.get("compareUnit") or "").lower().strip()

                # Weight is always in kg in the API
                weight_kg = source.get("weight")

                # Pack size from packageSize (e.g. "12STK")
                pack_size = None
                pkg_raw = source.get("packageSize", "")
                pack_match = re.search(r"(\d+)\s*STK", pkg_raw, re.IGNORECASE)
                if pack_match:
                    pack_size = int(pack_match.group(1))

                # --- Use comparePricePerUnit for accurate kg pricing ---
                # The API's pricePerUnit is the total item price, while
                # comparePricePerUnit is the real per-unit (e.g. per-kg) price.
                # For ALL items where compareUnit=kg, use comparePricePerUnit
                # as the authoritative kg price and set weight to 1kg.
                # This correctly handles:
                # - "pr Kg" items (e.g. Grillribbe at 205 kr/kg)
                # - Multi-kg packs (e.g. Ørret hel 3kg at 139 kr/kg)
                # - Regular weight items (e.g. 500g filet)
                if compare_price and compare_unit == "kg":
                    price = float(compare_price)
                    weight_kg = 1.0

                category = source.get("shoppingListGroupName", "")
                slug = source.get("slugifiedUrl", "")
                domain = store_name.lower()

                # Image URL: use imagePath from API directly
                # e.g. "7035620087509/kmh" → bilder.ngdata.no/7035620087509/kmh/medium.jpg
                image_path = source.get("imagePath", "")
                image_url = ""
                if image_path:
                    image_url = f"https://bilder.ngdata.no/{image_path}/medium.jpg"

                products.append(
                    {
                        "name": name,
                        "price": float(price),
                        "weight": float(weight_kg) if weight_kg else None,
                        "weight_unit": "kg" if weight_kg else None,
                        "pack_size": pack_size,
                        "category": category,
                        "store": store_name,
                        "source": "onlinestore",
                        "source_id": f"{domain}_{hit.get('_id', '')}",
                        "image": image_url,
                        "url": (
                            f"https://{domain}.no{slug}"
                            if slug
                            else f"https://{domain}.no/varer/{hit.get('_id', '')}"
                        ),
                    }
                )

            logger.info(
                "%s: fetched %d products (facet=%s)", store_name, len(products), facet
            )

        except Exception as e:
            logger.error("Failed to fetch from %s API: %s", store_name, e)

    return products


# ============================================================================
# ODA DOM scraper
# ============================================================================

_browser = None


async def _get_browser():
    """Shared Playwright browser instance."""
    global _browser
    if _browser is None:
        pw = await async_playwright().start()
        _browser = await pw.chromium.launch(headless=True)
    return _browser


async def _scrape_oda_page(url: str) -> list[dict[str, Any]]:
    """Scrape one Oda category page."""
    await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    browser = await _get_browser()
    page = await browser.new_page()
    products: list[dict[str, Any]] = []

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        articles = await page.query_selector_all("article")

        for article in articles:
            try:
                text = await article.inner_text()

                if "kr" not in text.lower():
                    continue

                # Price (e.g. "60,40 kr")
                price_match = re.search(r"(\d+[,\.]\d+)\s*kr", text)
                if not price_match:
                    continue
                price = float(price_match.group(1).replace(",", "."))

                # Name: first substantial non-price line
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                name = None
                for line in lines:
                    if (
                        len(line) > 5
                        and "kr" not in line.lower()
                        and "legg til" not in line.lower()
                        and "leveranse" not in line.lower()
                    ):
                        name = line
                        break

                if not name:
                    link = await article.query_selector('a[href*="/products/"]')
                    if link:
                        name = (
                            await link.get_attribute("title") or await link.inner_text()
                        )
                        name = name.strip().split("\n")[0]

                # Image: first product img (skip certification badges)
                image_url = ""
                imgs = await article.query_selector_all("img")
                for img_el in imgs:
                    src = await img_el.get_attribute("src") or ""
                    if "local_products" in src or "product" in src:
                        image_url = src
                        break

                if not name or not price:
                    continue

                # Unit price (e.g. "55,93 kr /kg")
                unit_price_match = re.search(r"(\d+[,\.]\d+)\s*kr\s*/\s*(\w+)", text)
                unit_price = None
                base_unit = None
                if unit_price_match:
                    unit_price = float(unit_price_match.group(1).replace(",", "."))
                    raw_unit = unit_price_match.group(2).lower()
                    if raw_unit in ("kg", "kilogram"):
                        base_unit = "kilogram"
                    elif raw_unit in ("l", "liter"):
                        base_unit = "liter"
                    elif raw_unit in ("stk",):
                        base_unit = "piece"

                # Pack size from detail text (e.g. "18 stk")
                pack_size = None
                weight_val = None
                weight_unit = None
                for line in lines:
                    stk_match = re.search(r"(\d+)\s*stk", line, re.IGNORECASE)
                    if stk_match and not pack_size:
                        pack_size = int(stk_match.group(1))
                    wt_match = re.search(
                        r"(\d+[,.]?\d*)\s*(kg|g|l|dl|ml)\b", line, re.IGNORECASE
                    )
                    if wt_match and not weight_val:
                        weight_val = float(wt_match.group(1).replace(",", "."))
                        weight_unit = wt_match.group(2).lower()

                # Infer category from URL
                category = ""
                url_lower = url.lower()
                if "egg" in url_lower:
                    category = "Egg"
                elif "melk" in url_lower:
                    category = "Melk"
                elif "kylling" in url_lower or "kjott" in url_lower:
                    category = "Kjøtt"
                elif "fisk" in url_lower or "sjomat" in url_lower:
                    category = "Fisk"

                products.append(
                    {
                        "name": name,
                        "price": price,
                        "weight": weight_val,
                        "weight_unit": weight_unit,
                        "pack_size": pack_size,
                        "unit_price": unit_price,
                        "base_unit": base_unit,
                        "category": category,
                        "store": "ODA",
                        "source": "onlinestore",
                        "source_id": f"oda_{name[:30].replace(' ', '_')}",
                        "image": image_url,
                        "url": url,
                    }
                )

            except Exception:
                pass

        logger.info("ODA: fetched %d products from %s", len(products), url)

    except Exception as e:
        logger.error("Failed to scrape Oda (%s): %s", url, e)
    finally:
        await page.close()

    return products


# ============================================================================
# Coop scraper (Extra, Coop Mega, Coop Prix, Obs)
# ============================================================================

COOP_CHAINS: dict[str, str] = {
    "extra": "Extra",
    "coop-mega": "Coop Mega",
    "coop-prix": "Coop Prix",
    "obs": "Obs",
}

COOP_URLS = [
    "https://www.coop.no/Weekly_offers_listing_page?chain=extra",
    "https://www.coop.no/Weekly_offers_listing_page?chain=coop-mega",
    "https://www.coop.no/Weekly_offers_listing_page?chain=coop-prix",
    "https://www.coop.no/Weekly_offers_listing_page?chain=obs",
]


async def _scrape_coop() -> list[dict[str, Any]]:
    """Scrape weekly offers from all Coop chains.

    Parses the HTML from coop.no weekly offers pages, extracting product
    name, unit price, image, and EAN. Skips percentage-only discounts.
    """
    all_products: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for url in COOP_URLS:
            chain_param = url.split("chain=")[-1]
            store_name = COOP_CHAINS.get(chain_param, chain_param)

            try:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                products = _parse_coop_html(resp.text, store_name)
                all_products.extend(products)
                logger.info("Coop %s: scraped %d products", store_name, len(products))
            except Exception:
                logger.exception("Failed to scrape Coop %s", store_name)

            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    return all_products


def _parse_coop_html(html: str, store_name: str) -> list[dict[str, Any]]:
    """Parse Coop weekly offers HTML into product dicts."""
    products: list[dict[str, Any]] = []
    articles = re.split(r"<article\b", html)

    for article in articles[1:]:
        # --- Product name & EAN ---
        name_m = re.search(
            r'href="/Weekly_offers_listing_page\?chain=[^&]+&amp;id=(\d+)">'
            r"([^<]+)</a>",
            article,
        )
        if not name_m:
            continue
        ean = name_m.group(1)
        name = name_m.group(2).strip()
        # Decode HTML entities
        name = name.replace("&amp;", "&").replace("&#x27;", "'")

        # --- Skip percentage-only discounts ---
        # Check for -NN% pattern in the price section (before h3)
        h3_idx = article.find("<h3")
        price_section = article[:h3_idx] if h3_idx > 0 else ""
        if re.search(r"-\d+%", price_section) and not re.search(
            r"<div[^>]*>\d{1,4}</div>", price_section
        ):
            logger.debug("Coop %s: skipping %%-only offer: %s", store_name, name)
            continue

        # --- Unit price (most reliable field) ---
        unit_m = re.search(r"Pr (\w+) ([\d,.]+)", article)
        if not unit_m:
            continue  # No unit price info → skip
        unit_type = unit_m.group(1).lower()  # kg, l, stk, etc.
        unit_price = float(unit_m.group(2).replace(",", "."))

        # --- Map unit to base_unit ---
        unit_map = {"kg": "kilogram", "l": "liter", "stk": "piece"}
        base_unit = unit_map.get(unit_type, unit_type)

        # --- Actual price from <div>NN</div><div>NN</div> ---
        price_m = re.search(
            r"<div[^>]*>(\d{1,4})</div>\s*(?:<style[^>]*>[^<]*</style>\s*)?<div[^>]*>(\d{2})</div>",
            price_section,
        )
        if not price_m:
            # Try single-number price: <div>NN</div></div>
            single_m = re.search(r"<div[^>]*>(\d{1,4})</div>\s*</div>", price_section)
            price = float(single_m.group(1)) if single_m else None
        else:
            price = float(f"{price_m.group(1)}.{price_m.group(2)}")

        # --- Promo detection (N for X) ---
        promos: list[str] = []
        nfor_m = re.search(r"(\d+)\s+for\s+(\d+)", article)
        if nfor_m:
            promos.append(f"{nfor_m.group(1)} for {nfor_m.group(2)}")

        # --- Image ---
        img_m = re.search(r'src="(https://cdcimg\.coop\.no/[^"]+)"', article)
        image = img_m.group(1).replace("&amp;", "&") if img_m else ""

        # --- Weight from name (e.g. "Kyllingfilet 1000g") ---
        weight = None
        weight_unit = None
        w_m = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|g|l|dl|ml|cl)\b", name, re.IGNORECASE)
        if w_m:
            w_val = float(w_m.group(1).replace(",", "."))
            w_unit = w_m.group(2).lower()
            # Convert to kg/l
            w_conversions = {
                "g": 0.001,
                "kg": 1,
                "ml": 0.001,
                "cl": 0.01,
                "dl": 0.1,
                "l": 1,
            }
            weight = w_val * w_conversions.get(w_unit, 1)
            weight_unit = (
                "kg"
                if w_unit in ("g", "kg")
                else "l" if w_unit in ("ml", "cl", "dl", "l") else w_unit
            )

        # --- Build URL ---
        product_url = (
            f"https://www.coop.no/Weekly_offers_listing_page?chain="
            f"{store_name.lower().replace(' ', '-')}&id={ean}"
        )

        products.append(
            {
                "source": "coop",
                "source_id": f"coop_{store_name.lower().replace(' ', '_')}_{ean}",
                "name": name,
                "price": price,
                "unit_price": unit_price,
                "base_unit": base_unit,
                "weight": weight,
                "weight_unit": weight_unit,
                "store": store_name,
                "store_logo": None,
                "url": product_url,
                "image": image,
                "pack_size": None,
                "promos": promos,
            }
        )

    return products


async def scrape_urls(urls: list[str]) -> list[dict[str, Any]]:
    """Scrape products from online store URLs.

    Parses each URL to determine the store and category, then calls
    the appropriate API or scraper.  Deduplicates facets so we don't
    hit the same API endpoint twice.
    """
    all_products: list[dict[str, Any]] = []
    seen_facets: set[str] = set()  # "domain|facet" → avoid duplicates

    for url in urls:
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lstrip("www.")

        # --- Oda: DOM scraping ---
        if "oda.com" in domain:
            prods = await _scrape_oda_page(url)
            all_products.extend(prods)
            continue

        # --- ngdata stores (Meny, Spar, Joker) ---
        result = _url_to_facet(url)
        if result is None:
            logger.warning("No facet mapping for URL: %s", url)
            continue

        domain, store_name, facet = result
        facet_key = f"{domain}|{facet}"
        if facet_key in seen_facets:
            continue  # already fetched this category
        seen_facets.add(facet_key)

        store_id, product_id = NGDATA_STORES[domain]
        prods = await _scrape_ngdata(store_id, product_id, store_name, facet)
        all_products.extend(prods)

    # --- Coop chains (Extra, Coop Mega, Coop Prix, Obs) ---
    try:
        coop_products = await _scrape_coop()
        all_products.extend(coop_products)
    except Exception:
        logger.exception("Coop scraping error")

    logger.info("Total online‐store products scraped: %d", len(all_products))
    return all_products
