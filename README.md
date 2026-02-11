# 🛒 Billigst Mat

> Norwegian grocery price tracker — find the cheapest food per unit across stores.

*Norsk matpristracker — finn billigste mat per enhet på tvers av butikker.*

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://github.com/YOUR_USERNAME/billigst-mat/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/billigst-mat/actions)

---

## 🇳🇴 Norsk

### Beskrivelse

**Billigst Mat** overvåker priser på dagligvarer fra Norges største matbutikker og sender e-postvarsler når prisene faller. Systemet normaliserer alle priser til kr/kg, kr/l eller kr/stk for rettferdig sammenligning.

### Støttede butikker

| Butikk | Datakilde | Type |
|--------|-----------|------|
| Meny | ngdata API | API |
| SPAR | ngdata API | API |
| Joker | ngdata API | API |
| Oda | Playwright | DOM scraping |
| Coop (Extra, Prix, Mega, Obs) | HTML | Web scraping |
| Kiwi, Rema 1000, m.fl. | eTilbudsavis | Tilbudsavis API |
| Holdbart | eTilbudsavis | Tilbudsavis API |

### Funksjoner

- 📊 **Pris per enhet** — Sammenligner kr/kg, kr/l, kr/stk på tvers av pakningsstørrelser
- 🔔 **Smarte varsler** — E-post når nye beste priser oppdages
- 📈 **Prishistorikk** — SQLite-database med historiske priser
- 🎯 **Kategorifiltrering** — Konfigurerbar whitelist/blacklist per produktgruppe
- 🔄 **Deduplisering** — Fjerner duplikater på tvers av datakilder

---

## 🇬🇧 English

### Description

**Billigst Mat** (Cheapest Food) monitors grocery prices across Norway's largest supermarkets and sends email alerts when prices drop. The system normalizes all prices to kr/kg, kr/l, or kr/piece for fair comparison.

### Supported Stores

| Store | Data Source | Type |
|-------|-------------|------|
| Meny | ngdata API | API |
| SPAR | ngdata API | API |
| Joker | ngdata API | API |
| Oda | Playwright | DOM scraping |
| Coop (Extra, Prix, Mega, Obs) | HTML | Web scraping |
| Kiwi, Rema 1000, etc. | eTilbudsavis | Flyer API |
| Holdbart | eTilbudsavis | Flyer API |

### Features

- 📊 **Unit pricing** — Compares kr/kg, kr/l, kr/piece across package sizes
- 🔔 **Smart alerts** — Email notifications when new best prices are found
- 📈 **Price history** — SQLite database tracking historical prices
- 🎯 **Category filtering** — Configurable whitelist/blacklist per product group
- 🔄 **Deduplication** — Removes duplicates across data sources

---

## 🏗️ Architecture / Arkitektur

```
┌─────────────────────────────────────────────────────────────────┐
│                        Data Sources                              │
├──────────────┬──────────────┬───────────────┬───────────────────┤
│ eTilbudsavis │   ngdata     │     Oda       │       Coop        │
│   (Tjek API) │  (Meny/Spar) │  (Playwright) │   (HTML scrape)   │
└──────┬───────┴──────┬───────┴───────┬───────┴─────────┬─────────┘
       │              │               │                 │
       └──────────────┴───────────────┴─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Normalizer    │  ← kr/kg, kr/l, kr/stk
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     Filters     │  ← whitelist/blacklist
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Deduplicator  │  ← cross-source dedup
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
      ┌───────▼───────┐ ┌────▼────┐ ┌──────▼──────┐
      │    Ranking    │ │   DB    │ │   Notify    │
      │ (top N/group) │ │ (SQLite)│ │  (Email)    │
      └───────────────┘ └─────────┘ └─────────────┘
```

---

## 🚀 Quick Start

### Prerequisites / Forutsetninger

- Python 3.11+
- [Playwright](https://playwright.dev/python/) (for Oda scraping)

### Installation / Installasjon

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/billigst-mat.git
cd billigst-mat

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -e .

# Install Playwright browsers
playwright install chromium
```

### Environment Variables / Miljøvariabler

Create a `.env` file / Lag en `.env` fil:

```env
# eTilbudsavis API (required)
ETILBUDSAVIS_API_KEY=your_api_key_here

# Email notifications (required)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_TO=recipient@example.com

# Optional: Geolocation (defaults to Oslo)
GEO_LAT=59.9139
GEO_LNG=10.7522
GEO_RADIUS=50000
```

### Running / Kjøring

```bash
# Normal run (all sources except Holdbart)
python -m src.main

# Holdbart-only mode
python -m src.main --holdbart
# or
python run_holdbart.py

# Verify online store scrapers work
python verify_stores.py
```

---

## 📁 Project Structure / Prosjektstruktur

```
billigst-mat/
├── src/
│   ├── main.py           # Main orchestrator
│   ├── config.py         # Configuration loader
│   ├── constants.py      # Shared constants
│   ├── db.py             # SQLite price history
│   ├── etilbudsavis.py   # eTilbudsavis/Tjek API client
│   ├── filters.py        # Whitelist/blacklist filtering
│   ├── normalizer.py     # Unit price normalization
│   ├── notify.py         # HTML/text email builder
│   ├── onlinestores.py   # Meny/Spar/Joker/Oda scrapers
│   ├── ranking.py        # Price ranking & triggers
│   └── url_validator.py  # Kassal URL validation
├── config/
│   └── groups.yaml       # Product category definitions
├── tests/                # Pytest test suite
├── data/                 # Runtime data (DB, cache)
└── pyproject.toml        # Project configuration
```

---

## ⚙️ Configuration / Konfigurasjon

Product categories are defined in `config/groups.yaml`:

```yaml
groups:
  - name: egg
    display_name: "🥚 Egg"
    base_unit: piece
    search_terms: ["egg 12", "egg 18"]
    include_any: ["egg"]
    exclude: ["pålegg", "sjokolade"]
    threshold: null  # optional: alert when price drops below

  - name: kyllingfilet
    display_name: "🍗 Kyllingfilet"
    base_unit: kilogram
    search_terms: ["kyllingfilet", "kyllingbryst"]
    include_any: ["kyllingfilet", "kyllingbryst"]
    exclude: ["pålegg", "nuggets", "panert"]
    threshold: 120  # kr/kg
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

---

## 📝 License / Lisens

MIT License — see [LICENSE](LICENSE) for details.

---

## 🤝 Contributing / Bidra

Contributions welcome! Please open an issue or pull request.

*Bidrag er velkomne! Åpne gjerne en issue eller pull request.*
