# Online Store Scraper Implementation

## Summary

Successfully implemented scrapers for **4 Norwegian online grocery stores**:

1. **Meny** - API scraping
2. **Spar** - API scraping  
3. **Joker** - API scraping
4. **Oda** - DOM scraping with Playwright

## Results

- **305 total products** scraped across all stores per run
- Breakdown:
  - Meny: ~115 products (eggs + milk)
  - Spar: ~67 products (eggs + milk)
  - Joker: ~54 products (eggs + milk)
  - Oda: ~69 products (eggs + milk)

## Technical Implementation

### Meny, Spar, Joker (ngdata API)
All three stores use the same backend API: `platform-rest-prod.ngdata.no`

**Key findings:**
- Each store has a unique store ID:
  - Meny: 1300
  - Spar: 1210
  - Joker: 1220
- Store-specific product IDs must be used in the API URL
- Category facets vary by store (different naming conventions)

**API Endpoint:**
```
GET https://platform-rest-prod.ngdata.no/api/products/{store_id}/{product_id}
Parameters:
  - page: 1
  - page_size: 100
  - full_response: true
  - fieldset: maximal
  - facets: Category,Allergen
  - facet: Categories:{category};ShoppingListGroups:{group}
  - showNotForSale: false
```

### Oda (DOM Scraping)
Oda uses client-side rendering with Next.js, requiring DOM scraping.

**Implementation:**
- Uses Playwright to render JavaScript
- Extracts product data from `<article>` elements
- Parses prices and names using regex patterns
- Shared browser instance for efficiency

**Categories scraped:**
- Eggs: `/categories/1283-meieri-ost-og-egg/50-egg/`
- Milk: `/categories/1283-meieri-ost-og-egg/97-melk/`

## Integration

The scraper integrates seamlessly with the existing food-alert system:

1. `/src/onlinestores.py` - Main scraper module
2. Called by `/src/main.py` alongside eTilbudsavis scraper
3. Products normalized and filtered same as catalog items
4. Included in email notifications with ranking

## Rate Limiting

- 1-3 second delays between requests
- Respects `robots.txt` conventions
- Minimal server load (API calls return bulk data)

## Future Improvements

Potential enhancements:
- Add more categories (meat, bread, etc.)
- Implement caching to reduce API calls
- Add more stores (Coop, Rema 1000, etc.)
- Better error handling and retries
- Parallel processing for faster scraping

## Files Modified

- `src/onlinestores.py` - Complete rewrite with all 4 stores
- Dependencies already installed (httpx, playwright)
