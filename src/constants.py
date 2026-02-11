"""Shared constants used across modules.

This module centralizes configuration values that were previously
scattered across multiple files, improving maintainability.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Unit display labels
# ---------------------------------------------------------------------------
UNIT_SHORT: dict[str, str] = {
    "kilogram": "kg",
    "liter": "l",
    "piece": "stk",
}

# ---------------------------------------------------------------------------
# Store exclusions
# ---------------------------------------------------------------------------

# Excluded globally from ALL sources (etilbudsavis, online stores, kassal).
# Matched case-insensitively against the item's "store" field.
EXCLUDED_STORES: list[str] = [
    "bunnpris",
    "nærbutikken",
    "naerbutikken",
    "engrosnett",
    "jacobs",
    "biltema",
]

# Additional exclusions for Kassal results specifically.
# Only eTilbudsavis may include results from these stores.
EXCLUDED_KASSAL_STORES: list[str] = [
    *EXCLUDED_STORES,
    "coop",
    "obs",
    "extra",
    "coop mega",
    "coop prix",
    "kiwi",
    "rema 1000",
    "rema",
    "oda",
]

# ---------------------------------------------------------------------------
# eTilbudsavis / Holdbart
# ---------------------------------------------------------------------------
HOLDBART_DEALER_ID = "pR2h9x"

# ---------------------------------------------------------------------------
# ngdata API store configuration (Meny, Spar, Joker)
# ---------------------------------------------------------------------------

# Store domain → (store_id, default_product_id)
NGDATA_STORES: dict[str, tuple[str, str]] = {
    "meny.no": ("1300", "7080001150488"),
    "spar.no": ("1210", "7080001097950"),
    "joker.no": ("1220", "7080001215606"),
}

# ---------------------------------------------------------------------------
# Store search URL templates
# ---------------------------------------------------------------------------
STORE_SEARCH_URLS: dict[str, str] = {
    "spar": "https://spar.no/sok?query={q}&expanded=products",
    "meny": "https://meny.no/sok?query={q}&expanded=products",
    "joker": "https://joker.no/sok?query={q}&expanded=products",
    "holdbart": "https://www.holdbart.no/search?q={q}",
    "europris": "https://www.europris.no/search?q={q}",
}
