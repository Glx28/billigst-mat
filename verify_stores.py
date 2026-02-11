#!/usr/bin/env python3
"""Final verification test - all stores."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.onlinestores import scrape_urls


async def main():
    """Verify all stores are working."""
    print("\n" + "=" * 70)
    print("FINAL VERIFICATION - ALL ONLINE STORES")
    print("=" * 70)

    products = await scrape_urls([])

    # Group by store
    by_store = {}
    for p in products:
        store = p["store"]
        by_store.setdefault(store, []).append(p)

    # Verify each store
    required_stores = {"MENY", "SPAR", "JOKER", "ODA"}
    found_stores = set(by_store.keys())

    print("\n✅ Store Status:")
    all_ok = True
    for store in sorted(required_stores):
        count = len(by_store.get(store, []))
        status = "✅ OK" if count > 0 else "❌ FAILED"
        print(f"  {store:10s}: {count:3d} products {status}")
        if count == 0:
            all_ok = False

    print(f"\nTotal: {len(products)} products")

    if all_ok and len(products) >= 200:
        print("\n🎉 ALL STORES WORKING PERFECTLY!")
        return 0
    else:
        print("\n⚠️  Some stores failed or low product count")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
