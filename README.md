# Core vocabulary warehouse

Independent multilingual dictionary platform.

Postgres is the source of truth. JSON is a portable export.

```
GitHub / academic dumps   →   ingest (once)
                              ↓
                         PostgreSQL 14+
                              ↓
                    SQL ranks per language
                              ↓
                    out/core_vocabulary.json
```

## Contract

- One concept = one WordNet synset (`eat.v.01`).
- `rank` lives on `terms.<lang>`, never on the concept.
- `phonology` declares pronunciation systems **per language**. Term `readings` may omit a system or set it `null`; unknown ids are invalid. Fill later via API.
- Catalog = **union of top-N lemmas per language**.
- Missing translation → omit the key. Never invent a lemma.
- `rank <= 1000|3000|5000|8000|12000` is the slice.

```json
{
  "version": 1,
  "phonology": {
    "zh": {
      "systems": [
        { "id": "pinyin", "label": "Hanyu Pinyin", "script": "latn", "learner": true },
        { "id": "zhuyin", "label": "Zhuyin / Bopomofo", "script": "bopo", "learner": false },
        { "id": "ipa", "label": "IPA", "script": "ipa", "learner": false }
      ]
    }
  },
  "topN": 12000,
  "count": 28412,
  "concepts": [
    {
      "id": "eat.v.01",
      "pos": "verb",
      "meaning": "take in solid food",
      "terms": {
        "en": { "text": "eat", "rank": 163, "readings": { "ipa": "/iːt/", "ipa-us": null } },
        "vi": { "text": "ăn", "rank": 48 },
        "zh": { "text": "吃", "rank": 77, "readings": { "pinyin": "chī" } }
      }
    }
  ]
}
```

```python
vi_3k = [c for c in catalog["concepts"] if c["terms"].get("vi", {}).get("rank", 10**9) <= 3000]
```

## Layers

| Layer | What | Tables / files |
|---|---|---|
| Bronze | Raw dumps, gitignored | `.cache/` (OMW, Kaikki, NLTK) |
| Silver | Normalized warehouse | `languages`, `lemmas`, `synsets`, `sense_lemmas`, `readings` |
| Gold | Analysis mart | `concept_ranks` |
| Publish | Portable artifact | `out/core_vocabulary.json` |

## Setup

Requires PostgreSQL 14+ on this machine (default `postgresql:///dictionary?host=/tmp`).

```bash
createdb dictionary
make install
export DATABASE_URL=postgresql:///dictionary?host=/tmp
make migrate
```

## Console

```bash
make install
make app            # http://127.0.0.1:8787
```

Coverage, catalog browse, pivot export (default ZH 3000), operations. Localhost only. No API keys.

## Commands

```bash
make smoke          # tiny ingest + rank + export + validate
make ingest         # full dumps (Wiktionary once)
make rank           # rebuild ranks — seconds
make export         # union JSON
make export-zh-3000 # Chinese 3000 + 34 translations
make validate
```

Re-rank after changing `--top-n` or function-word lists. Do not reload dumps.

## Sources

| Source | Role |
|---|---|
| wordfreq | Frequency / zipf / per-language rank seed |
| Princeton WordNet | Synset identity + English gloss |
| OMW 1.4 | Gold alignments |
| Kaikki English Wiktionary | Gap fill (script-filtered) |
| pypinyin / kakasi / korean-romanizer | Readings |

No machine translation. `th` / `te` / `sw` have no wordfreq list — they receive terms but do not seed the union.

## Layout

```
sql/                migrations
warehouse/          ingest, rank, export, CLI
schema.py           JSON + ISO contract
validate.py         export validator
```
