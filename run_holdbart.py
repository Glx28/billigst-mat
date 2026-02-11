#!/usr/bin/env python3
"""Run food-alert in Holdbart-only mode.

Only processes offers from Holdbart. Sends an email only if a Holdbart
product is the best price (#1) in at least one category.

Usage:
    python run_holdbart.py
    # or equivalently:
    python -m src.main --holdbart
"""

import asyncio

from src.main import run

if __name__ == "__main__":
    asyncio.run(run(mode="holdbart"))
