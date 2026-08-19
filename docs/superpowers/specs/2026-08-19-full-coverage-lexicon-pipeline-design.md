# Design: Full-coverage 12k × 35 lexicon pipeline

Date: 2026-08-19
Status: Approved (design agreed with user in brainstorming)

## Problem

`lexicon-core.db` is concept-centric: a fixed set of 12,000 English-pivoted
synsets. Terms per language are whatever Open Multilingual WordNet + English
Wiktionary translations happened to map onto those synsets.

Current seed (`frontend-extension/public/vocabulary/lexicon-core.db`):

- 12,000 concepts, 35 languages, 232,887 terms
- English: 12,000 (100%)
- Finnish / French / Japanese / Spanish: ~9k–12k
- Vietnamese: 4,436 (37%)
- Tamil: 2,127 (17.7%)

This is not a product gap in ranking (every existing term is Zipf-ranked). It is
an **ingestion coverage gap**: Tier-3 languages have no academic WordNet and
were only filled from English-Wiktionary `translations`.

## Goal

Fill every empty `(concept, lang)` cell for the existing 12,000 concepts and 35
languages in `schema.LANGUAGES`.

Target matrix:

- 12,000 concepts × 35 languages = **420,000 terms**
- 100% native `meaning` on every term
- readings via existing `readings_for()` / `system_ids_for(lang)` (≥ 99.99%)

Out of scope for this spec:

- expanding the concept set to 24,000
- changing frontend game UI, SRS mix, or SQLite schema shape
- inventing IPA when a phonology engine cannot produce a reading

## Approach

Multi-source dictionary ingestion first, LLM only for remaining empty cells.

```
Tầng 1  Ingest mở rộng (Wiktextract đa ngữ + Wikidata lexemes)
        → core.lemmas + core.sense_lemmas

Tầng 2  Rank lại (sql/002_ranks.sql, unchanged selection order)
        → core.concept_ranks

Tầng 3  LLM fallback (Gemini via warehouse/llm.py)
        → only empty (synset_id, lang) after tầng 1+2

Tầng 4  Phonology + gloss + export-sqlite
        → lexicon-core.db.gz
```

## Architecture

Keep Postgres schema in `sql/001_schema.sql`. Add sources, do not invent a
second catalog.

### New sources (`core.sources`)

| id           | role                                      |
|--------------|-------------------------------------------|
| `wiktextract`| native-language Wiktionary dumps (kaikki) |
| `wikidata`   | lexeme / translation / sense links        |
| `llm`        | gap-fill only                             |

Existing `wordnet`, `omw-1.4`, `wiktionary` (English dump) stay as-is.

### Tầng 1 — ingest

New modules (same style as `warehouse/ingest/wiktionary.py`):

- `warehouse/ingest/wiktextract_native.py`
  - download Kaikki dumps for languages in `LANGUAGES` that are not English
  - map a translation/sense to an existing `core.synsets.id` via English lemma
    + POS already in `core.sense_lemmas`
  - skip if `script_ok(lang, text)` fails or lemma is a function word
- `warehouse/ingest/wikidata_lexemes.py`
  - download Wikidata lexeme dump (or SPARQL batched by synset/lexeme id)
  - attach lemmas to synsets only when a Wikidata sitelink / lexical category
    maps to an existing WordNet synset id
  - never create new synsets

Both writers:

```
INSERT INTO core.lemmas (lang, text, normalized, zipf, wordfreq_rank)
ON CONFLICT (lang, normalized) DO UPDATE zipf / rank if incoming is better

INSERT INTO core.sense_lemmas (synset_id, lemma_id, source_id)
ON CONFLICT DO NOTHING
```

Zipf / `wordfreq_rank` still come from `warehouse/ingest/wordfreq.py` (join by
normalized lemma). New lemmas without a wordfreq row stay `zipf NULL` and lose
to frequency-ranked siblings in `002_ranks.sql`.

### Tầng 2 — rank

`compute_ranks(top_n=12000)` unchanged:

1. exclude function words
2. prefer lemma that spans the fewest synsets (specificity)
3. then higher Zipf
4. catalog still requires an English term and ≥ 2 languages on the synset
   (already true for the 12k set)

After re-rank, coverage per language rises by however many synsets now have a
non-English headword from tầng 1.

### Tầng 3 — LLM gap-fill

Input: every `(synset_id, lang)` in the 12k catalog with no row in
`core.concept_ranks`.

Prompt (extend `CURATION_SYSTEM_PROMPT` in `warehouse/llm.py`):

- English headword, POS, `definition_en`
- optional candidate list from leftover ingest (rejected for rank, not empty)
- ask for exactly one learner-natural lemma for THIS sense
- JSON only: `{"<lang>": "<lemma>"}`

Guards:

- cache key `(synset_id, lang)` on disk (same pattern as gloss cache)
- `script_ok` + `is_usable_lemma` or reject
- back-translate required: lemma → English; if the returned English lemma is
  not in that synset's English lemmas and not a close synonym listed in the
  prompt, reject, retry once, then leave empty and log
- never overwrite a `concept_ranks` / `sense_lemmas` row whose `source_id` is
  `wordnet`, `omw-1.4`, `wiktionary`, `wiktextract`, or `wikidata`
- write accepted rows with `source_id = 'llm'`

Job runner: existing `warehouse/jobs.py` (`JobContext` progress, cancel,
checkpoint every N synsets). CLI: `python -m warehouse ingest --only llm-gaps`
and a console button on the B2B app.

### Tầng 4 — attach + export

Unchanged exporters, run in order:

1. `build_readings.readings_for(lang, text)` — never invent IPA
2. gloss cache / `batch_populate_glosses` for native `meaning`
3. `export_sqlite` → `out/lexicon-core.db` + `.gz`
4. copy into `frontend-extension/public/vocabulary/lexicon-core.db.gz`

Frontend schema stays:

```
concepts(id, pos, meaning, meaning_lang)
terms(concept_id, lang, text, meaning, rank, readings)
```

No new columns required for this spec. Provenance stays in Postgres
(`core.sense_lemmas.source_id`). The shipped SQLite seed remains the
learner-facing slice.

## Data flow

```
Kaikki native dumps ─┐
Wikidata lexemes ────┼─► Postgres lemmas / sense_lemmas
existing OMW/WN/en ──┘
         │
         ▼
   compute_ranks(12000)
         │
         ├─ missing (synset, lang) ─► LLM + cache ─► sense_lemmas (llm)
         │
         ▼
   readings_for + gloss cache
         │
         ▼
   lexicon-core.db.gz  (12,000 × 35 terms)
```

## Error handling

| Failure                         | Behaviour                                      |
|---------------------------------|------------------------------------------------|
| dump download fail              | retry URLs; job error; no partial source flip  |
| unmapped Wikidata lexeme        | skip; do not create synset                     |
| LLM timeout / bad JSON          | retry 1; then skip cell + log                  |
| back-translate mismatch         | retry 1; then skip cell + log                  |
| script / function-word reject   | skip cell                                      |
| phonology engine missing        | omit that reading key; do not invent IPA       |
| job cancel                      | persist cache; resume from last checkpoint     |

## Testing

Warehouse (pytest in `/Users/admin/Documents/big-data`):

- parser fixtures: one Wiktextract line and one Wikidata lexeme → correct
  `sense_lemmas` row or skip
- rank: after a fixture ingest, a previously empty `(synset, vi)` gets a rank
- LLM cache: second call does not hit the network
- gold lock: fixture with `source_id=omw-1.4` is not replaced by LLM
- export gate: for a tiny catalog (e.g. 3 synsets × 35 langs) every language
  has 3 terms after gap-fill

Release gate (full catalog):

- `SELECT lang, COUNT(*) FROM terms GROUP BY lang` → every `LANGUAGES` code
  equals 12,000
- `meaning` non-null on 100% of terms
- `readings` non-null on ≥ 99.99% of terms

Frontend: no code change required. After seed copy, `npm run typecheck` and
existing `coreQueriesReadings` tests still pass.

## Success criteria

1. 35 / 35 languages at 12,000 terms in the exported seed.
2. Provenance: every new lemma traceable to `wiktextract`, `wikidata`, or `llm`.
3. Gold rows from OMW / English Wiktionary / WordNet unchanged.
4. Phonology rules from the 2026-08-19 readings spec still hold.
5. Job is resumable and does not require a full re-ingest after cancel.
