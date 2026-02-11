"""Configuration loader for food-alert."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def load_groups() -> dict:
    """Load group definitions from YAML config."""
    with open(CONFIG_DIR / "groups.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- API keys / env ---
ETILBUDSAVIS_API_KEY = os.getenv("ETILBUDSAVIS_API_KEY", "")
ETILBUDSAVIS_API_SECRET = os.getenv("ETILBUDSAVIS_API_SECRET", "")
KASSAL_API_TOKEN = os.getenv("KASSAL_API_TOKEN", "")

# Email — supports both SMTP_USER/EMAIL_TO and EMAIL_SENDER/EMAIL_RECIPIENT
SMTP_USER = os.getenv("SMTP_USER") or os.getenv("EMAIL_SENDER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") or os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO") or os.getenv("EMAIL_RECIPIENT", "")

# Auto-detect SMTP host from sender address if not explicitly configured
_smtp_host_env = os.getenv("SMTP_HOST", "")
if _smtp_host_env:
    SMTP_HOST = _smtp_host_env
elif "yahoo" in SMTP_USER:
    SMTP_HOST = "smtp.mail.yahoo.com"
else:
    SMTP_HOST = "smtp.gmail.com"

# Override if the explicit host doesn't match the sender domain
if SMTP_HOST == "smtp.gmail.com" and "yahoo" in SMTP_USER:
    SMTP_HOST = "smtp.mail.yahoo.com"

SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Geo for eTilbudsavis (lat/lng/radius in metres)
GEO_LAT = os.getenv("GEO_LAT", "59.9139")  # Oslo default
GEO_LNG = os.getenv("GEO_LNG", "10.7522")
GEO_RADIUS = os.getenv("GEO_RADIUS", "30000")  # 30 km


def load_store_urls() -> dict[str, list[str]]:
    """Load online store URLs from online_store_links.txt.

    Returns dict mapping store names to lists of URLs.
    Example: {"oda": ["https://oda.com/...", ...], "spar": [...]}
    """
    links_file = BASE_DIR / "online_store_links.txt"
    if not links_file.exists():
        return {}

    store_urls: dict[str, list[str]] = {}
    current_store = None

    with open(links_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Store header like [oda]
            if line.startswith("[") and line.endswith("]"):
                current_store = line[1:-1].lower()
                store_urls[current_store] = []
            # URL
            elif line.startswith("http") and current_store:
                store_urls[current_store].append(line)

    return store_urls
