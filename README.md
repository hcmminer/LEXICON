# 🌐 Lexicon — Multilingual Core Vocabulary Data Platform

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-336791.svg)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An enterprise-grade, high-performance linguistic data warehouse and dictionary compilation engine for **35 languages**. 

Designed as a **single source of truth** for international vocabulary ranking, cross-lingual sense alignment, pronunciation metadata (IPA, Pinyin, Hiragana, Romaja...), and customized dataset exports (e.g., *Chinese Top 3000 with Vietnamese & English alignments*).

---

## 🌟 Key Highlights

- **🎯 True Per-Language Frequency Ranking**: Frequency is a linguistic property of each language, not an artificial global concept. Each language has its own Zipf score and 1-based popularity rank.
- **🔗 Concept-Centric Alignment (WordNet & OMW)**: Uses gold-standard Princeton WordNet synsets as language-neutral semantic anchors, eliminating polysemy errors.
- **⚡ Medallion Architecture (PostgreSQL 14+)**: Raw dumps (Bronze) → Normalized warehouse tables (Silver) → Ranked analytical mart (Gold) → Artifact JSON exports (Publish).
- **🖥️ Built-in Web Console & Live Inspector**: Interactive FastAPI web application (`:8787`) to browse, search, preview, and download custom vocabulary packs with selective language filtering.
- **🗣️ Typed Phonology DTOs**: Standardized pronunciation slots declared per language (`ipa`, `pinyin`, `zhuyin`, `hiragana`, `romaji`, `rr`, `rtgs`, `iast`, `iso9`, `alalc`...).
- **📦 Fully Extensible & Scalable**: Seamlessly slice from **1,000 → 3,000 → 5,000 → 12,000 → 50,000+** words without schema modifications.

---

## 📐 Data Architecture

```
                       +---------------------------------------+
                       |      Gold Academic Sources (Bronze)    |
                       |  wordfreq · WordNet · OMW · Kaikki    |
                       +---------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                           PostgreSQL Warehouse (Silver)                           |
|  core.languages · core.lemmas · core.synsets · core.sense_lemmas · core.readings  |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                             Analytical Mart (Gold)                                |
|             core.concept_ranks (Window partitioned per-language Zipf rank)        |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                            Publishing & UI Layer                                  |
|     FastAPI Web Console (:8787)  ·  Selective Pivot Exports  ·  Gzip JSON (.gz)   |
+-----------------------------------------------------------------------------------+
```

---

## 📋 JSON Schema Contract

Exported artifacts follow an extensible, type-safe envelope format:

```json
{
  "version": 1,
  "generatedAt": "2026-08-17T08:50:00Z",
  "sources": ["wordfreq", "omw-1.4", "wiktextract"],
  "languages": ["zh", "vi", "en"],
  "phonology": {
    "zh": {
      "systems": [
        { "id": "pinyin", "label": "Hanyu Pinyin", "script": "latn", "learner": true },
        { "id": "zhuyin", "label": "Zhuyin / Bopomofo", "script": "bopo", "learner": false },
        { "id": "ipa", "label": "IPA", "script": "ipa", "learner": false }
      ]
    },
    "vi": {
      "systems": [
        { "id": "ipa", "label": "IPA", "script": "ipa", "learner": true }
      ]
    },
    "en": {
      "systems": [
        { "id": "ipa", "label": "IPA", "script": "ipa", "learner": true },
        { "id": "ipa-us", "label": "IPA (General American)", "script": "ipa", "learner": false }
      ]
    }
  },
  "topN": 3000,
  "count": 3000,
  "pivot": "zh",
  "concepts": [
    {
      "id": "water.n.01",
      "pos": "noun",
      "meaning": "a clear liquid essential for life",
      "terms": {
        "zh": {
          "text": "水",
          "rank": 1,
          "readings": {
            "pinyin": "shuǐ",
            "zhuyin": "ㄕㄨㄟˇ"
          }
        },
        "vi": {
          "text": "nước",
          "rank": 211
        },
        "en": {
          "text": "water",
          "rank": 632,
          "readings": {
            "ipa": "/ˈwɔːtər/"
          }
        }
      }
    }
  ]
}
```

### Consumption Rules
1. **Omit When Missing**: If a secondary translation does not exist in gold sources, the key is omitted entirely (no empty string or `null` keys).
2. **True Slicing**: Slicing the top 3,000 words in Vietnamese is as simple as:
   ```python
   vi_3k = [c for c in catalog["concepts"] if c["terms"].get("vi", {}).get("rank", 10**9) <= 3000]
   ```

---

## 🚀 Quickstart & Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 14+ running locally

### 1. Installation
```bash
git clone https://github.com/your-org/big-data.git
cd big-data

# Create virtual environment and install dependencies
make install
```

### 2. Database Initialization & Ingestion
```bash
# Create database
createdb dictionary

# Set connection string (default uses unix socket)
export DATABASE_URL=postgresql:///dictionary?host=/tmp

# Run schema migrations
make migrate

# Ingest linguistic datasets (WordNet, OMW 1.4, wordfreq, Wiktextract)
make ingest

# Calculate window-partitioned ranks (instantaneous SQL calculation)
make rank
```

### 3. Launch Web Management Console
```bash
make app
```
Open **`http://127.0.0.1:8787`** in your browser to access the management UI.

---

## 🖥️ Web Console Features

| Route | View | Capabilities |
|---|---|---|
| `/` | **Coverage Dashboard** | Real-time table metrics, live lemma counts per language, and ingestion logs. |
| `/catalog` | **Interactive Explorer** | Search lemmas, filter by POS, pivot language, and maximum rank limit. |
| `/catalog/{id}` | **Concept Term Sheet** | Complete 35-language alignment view with per-language phonology slots. |
| `/export` | **Custom Pack Exporter** | Configure Pivot, Volume (1k–100k), select target languages, and **Live Preview** table/JSON before downloading. |
| `/ops` | **Operations Hub** | Trigger non-blocking asynchronous maintenance jobs (Re-rank, Ingest steps, Cache flush). |

---

## 🛠️ CLI Operations

```bash
# Export the complete 35-language union catalog
make export

# Export a tailored Chinese Top 3,000 pack
make export-zh-3000

# Validate generated JSON against integrity schema
make validate

# Run automated pipeline smoke test
make smoke
```

---

## 🌍 Supported Languages (35)

| Code | Language | Script | Phonology Support |
|---|---|---|---|
| `en` | English | Latin | IPA, IPA (US), IPA (GB) |
| `vi` | Vietnamese | Latin | IPA |
| `zh` | Chinese (Simplified) | Hanzi | Hanyu Pinyin, Zhuyin/Bopomofo, IPA |
| `ja` | Japanese | Kanji/Kana | Hiragana, Hepburn Romaji, IPA |
| `ko` | Korean | Hangul | Revised Romanization (RR), IPA |
| `hi` | Hindi | Devanagari | IAST Romanization, IPA |
| `es` | Spanish | Latin | IPA |
| `fr` | French | Latin | IPA |
| `de` | German | Latin | IPA |
| `pt` | Portuguese | Latin | IPA |
| `ru` | Russian | Cyrillic | ISO 9 Romanization, IPA |
| `ar` | Arabic | Arabic | ALA-LC Romanization, IPA |
| `bn` | Bengali | Bengali | ISO 15919, IPA |
| `id` | Indonesian | Latin | IPA |
| `ms` | Malay | Latin | IPA |
| `th` | Thai | Thai | RTGS Romanization, IPA |
| `tr` | Turkish | Latin | IPA |
| `it` | Italian | Latin | IPA |
| `nl` | Dutch | Latin | IPA |
| `pl` | Polish | Latin | IPA |
| `uk` | Ukrainian | Cyrillic | ISO 9 Romanization, IPA |
| `el` | Greek | Greek | ELOT 743 Romanization, IPA |
| `cs` | Czech | Latin | IPA |
| `sv` | Swedish | Latin | IPA |
| `da` | Danish | Latin | IPA |
| `fi` | Finnish | Latin | IPA |
| `no` | Norwegian | Latin | IPA |
| `hu` | Hungarian | Latin | IPA |
| `ro` | Romanian | Latin | IPA |
| `he` | Hebrew | Hebrew | ALA-LC Romanization, IPA |
| `fa` | Persian | Perso-Arabic | UN Romanization, IPA |
| `ur` | Urdu | Perso-Arabic | ALA-LC Romanization, IPA |
| `ta` | Tamil | Tamil | ISO 15919, IPA |
| `te` | Telugu | Telugu | ISO 15919, IPA |
| `sw` | Swahili | Latin | IPA |

---

## 📂 Project Structure

```
big-data/
├── Makefile                     # Automation tasks (install, migrate, ingest, app)
├── README.md                    # Platform documentation & API reference
├── LICENSE                      # MIT Open Source License
├── requirements.txt             # Locked Python runtime dependencies
├── schema.py                    # Domain constants, ISO codes & envelope models
├── phonology.py                 # Pronunciation systems DTO registry
├── validate.py                  # Integrity & strict validation test suite
├── sql/
│   ├── 001_schema.sql           # DDL: Silver & Gold table schemas & indexes
│   └── 002_ranks.sql            # Analytical rank window query
├── warehouse/
│   ├── config.py                # Environment & database configurations
│   ├── db.py                    # PostgreSQL connection pooling & execution helpers
│   ├── textutil.py              # Unicode NFKC, script checks & stopword filters
│   ├── build_readings.py        # Reading generators (pypinyin, kakasi, romanizer)
│   ├── queries.py               # Analytical warehouse search & summary queries
│   ├── rank.py                  # Rank compilation orchestrator
│   ├── export_json.py           # Pack generator & JSON serializer
│   ├── jobs.py                  # Background task worker & execution lock
│   ├── web.py                   # FastAPI application & REST/HTML endpoints
│   └── ingest/
│       ├── seed.py              # Reference language & function word seeding
│       ├── wordfreq.py          # Wordfreq Zipf score ingestion
│       ├── wordnet_omw.py       # Princeton WordNet & OMW 1.4 ingestion
│       ├── wiktionary.py        # Wiktextract translation gap-filling
│       └── readings.py          # Bulk pronunciation generator
└── web/
    ├── static/
    │   └── app.css              # Industrial B2B CSS design system
    └── templates/
        ├── base.html            # Global application layout & sidebar
        ├── coverage.html        # Warehouse coverage analytics dashboard
        ├── catalog.html         # Multilingual concept search & browser
        ├── concept.html         # Detailed term sheet & phonology inspector
        ├── export.html          # Custom pack builder & Live Data Inspector
        └── ops.html             # Operational control plane & job status
```

---

## 📜 License

This project is open-source under the **MIT License**. Linguistic datasets loaded into the warehouse retain their respective upstream licenses (Princeton WordNet License, CC BY-SA for Wiktionary, and OMW research licenses).
