# Full-coverage 12k × 35 Lexicon Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill every empty `(concept, lang)` cell so the exported seed has 12,000 terms × 35 languages (420,000 terms) via native dictionary ingest first and LLM only for leftovers.

**Architecture:** Pure parsers turn Kaikki native dumps and Wikidata lexemes into `(synset_id, lang, lemma)` links; thin ingest writers upsert `core.lemmas` / `core.sense_lemmas`. Re-run existing `compute_ranks`. LLM gap-fill writes only missing `concept_ranks` rows (`source_id='llm'`), never gold. Then existing readings + gloss + `export_sqlite`.

**Tech Stack:** Python 3.12, Postgres (`core.*`), pytest, existing `warehouse.llm.call_chat_json` (Gemini via OpenAI-compatible client), Kaikki JSONL, Wikidata lexeme dump.

## Global Constraints

- Concept set stays the existing 12,000 WordNet synsets. Never insert a new `core.synsets` row.
- Languages are exactly `schema.LANGUAGES` (35 codes). Target: every lang has 12,000 terms in the exported SQLite seed.
- Native dump source id is the already-seeded `wiktextract-multilingual` (do not reuse `wiktextract`, which is the English dump).
- New source ids: `wikidata`, `llm`. Add them to `sql/001_schema.sql` `INSERT INTO core.sources`.
- Gold lock: never overwrite `sense_lemmas` / `concept_ranks` whose `source_id` is in `{"wordnet", "omw-1.4", "wiktionary", "wiktextract", "wiktextract-multilingual", "wikidata"}`.
- LLM only fills `(synset_id, lang)` with no `concept_ranks` row after ingest + rank.
- Back-translate is required: proposed lemma → English; accept only if that English lemma is in the synset's English lemmas (or a synonym listed in the prompt). Retry once, then skip + log.
- Readings only from `warehouse.build_readings.readings_for` / `phonology.system_ids_for`. Never invent IPA.
- Jobs use `warehouse.jobs.JobContext` (progress, cancel, checkpoint). Cache LLM results by `(synset_id, lang)`.
- Frontend schema unchanged. After export, copy `out/lexicon-core.db.gz` into `frontend-extension/public/vocabulary/`.
- Tests stay Postgres-free (match existing suite). Parsers and policy functions are pure.

## File map

- Create: `warehouse/ingest/wiktextract_native.py` — parse Kaikki native entries; ingest writer
- Create: `warehouse/ingest/wikidata_lexemes.py` — parse Wikidata lexemes; ingest writer
- Create: `warehouse/ingest/llm_gaps.py` — cache, accept, back-translate, gap job
- Create: `tests/test_wiktextract_native.py`
- Create: `tests/test_wikidata_lexemes.py`
- Create: `tests/test_llm_gaps.py`
- Create: `tests/test_coverage_gate.py`
- Modify: `warehouse/download_sources.py` — Kaikki native URLs + Wikidata lexeme dump
- Modify: `sql/001_schema.sql` — `wikidata`, `llm` source rows
- Modify: `warehouse/cli.py` — `--only wiktextract-native|wikidata|llm-gaps`
- Modify: `warehouse/web.py` — OPS buttons + `_job` branches

---

### Task 1: Native Wiktextract parser

**Files:**
- Create: `warehouse/ingest/wiktextract_native.py`
- Test: `tests/test_wiktextract_native.py`

**Interfaces:**
- Consumes: `schema.WIKT_CODE_TO_ISO`, `schema.WIKT_POS_TO_OURS`, `warehouse.textutil.normalize`, `is_usable_lemma`, `script_ok`
- Produces: `native_entry_links(entry: dict, en_index: dict[tuple[str, str], list[str]]) -> list[tuple[str, str, str]]` returning `(synset_id, lang, lemma)`

- [ ] **Step 1: Write the failing test**

```python
from warehouse.ingest.wiktextract_native import native_entry_links


def test_native_entry_maps_via_english_translation():
    en_index = {("water", "noun"): ["water.n.01"]}
    entry = {
        "word": "nước",
        "lang_code": "vi",
        "pos": "noun",
        "senses": [{"translations": [{"code": "en", "word": "water"}]}],
    }
    assert native_entry_links(entry, en_index) == [("water.n.01", "vi", "nước")]


def test_native_entry_skips_unknown_english_and_bad_script():
    en_index = {("water", "noun"): ["water.n.01"]}
    unknown = {"word": "xyzzy", "lang_code": "vi", "pos": "noun", "senses": [{"translations": [{"code": "en", "word": "not-a-synset"}]}]}
    latin_as_vi = {"word": "water", "lang_code": "vi", "pos": "noun", "senses": [{"translations": [{"code": "en", "word": "water"}]}]}
    assert native_entry_links(unknown, en_index) == []
    assert native_entry_links(latin_as_vi, en_index) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wiktextract_native.py -q`
Expected: FAIL with `ModuleNotFoundError` or `native_entry_links` not defined

- [ ] **Step 3: Write minimal implementation**

In `warehouse/ingest/wiktextract_native.py`:

```python
from __future__ import annotations

from schema import WIKT_CODE_TO_ISO, WIKT_POS_TO_OURS
from warehouse.textutil import is_usable_lemma, normalize, script_ok

OURS_TO_WN = {"noun": ("n",), "verb": ("v",), "adjective": ("a", "s"), "adverb": ("r",)}


def _english_words(entry: dict) -> list[str]:
    found: list[str] = []
    buckets = []
    if isinstance(entry.get("translations"), list):
        buckets.append(entry["translations"])
    for sense in entry.get("senses") or []:
        if isinstance(sense, dict) and isinstance(sense.get("translations"), list):
            buckets.append(sense["translations"])
    for group in buckets:
        for item in group:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or item.get("lang_code") or "")
            if WIKT_CODE_TO_ISO.get(code) != "en":
                continue
            word = item.get("word")
            if isinstance(word, str) and word.strip():
                found.append(word.strip())
    return found


def native_entry_links(entry: dict, en_index: dict[tuple[str, str], list[str]]) -> list[tuple[str, str, str]]:
    lemma = str(entry.get("word") or "").strip()
    lang = WIKT_CODE_TO_ISO.get(str(entry.get("lang_code") or ""))
    pos = WIKT_POS_TO_OURS.get(str(entry.get("pos") or ""))
    if not lemma or lang is None or lang == "en" or pos is None:
        return []
    if not is_usable_lemma(lemma) or not script_ok(lang, lemma):
        return []
    links: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for en in _english_words(entry):
        for wn_pos in OURS_TO_WN.get(pos, ()):
            for synset_id in en_index.get((normalize(en), wn_pos), [])[:3]:
                if synset_id not in seen:
                    seen.add(synset_id)
                    links.append((synset_id, lang, lemma))
    return links
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wiktextract_native.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_wiktextract_native.py warehouse/ingest/wiktextract_native.py
git commit -m "feat(ingest): parse native Kaikki entries onto existing synsets"
```

---

### Task 2: Register native dumps and ingest writer

**Files:**
- Modify: `warehouse/download_sources.py`
- Modify: `warehouse/ingest/wiktextract_native.py` (add `ingest_wiktextract_native`)
- Modify: `tests/test_wiktextract_native.py`

**Interfaces:**
- Consumes: `native_entry_links`, `warehouse.download_sources.ensure_data_source`, `warehouse.db.connect` / `executemany`
- Produces: `KAIKKI_NATIVE_LANGS: dict[str, str]` (iso → Kaikki English language name); `ingest_wiktextract_native(max_entries: int | None = None) -> None`

Kaikki URL pattern (verbatim):

`https://kaikki.org/dictionary/{Name}/kaikki.org-dictionary-{Name}.jsonl.gz`

ISO → Name map (all `LANGUAGES` except `en`):

```python
KAIKKI_NATIVE_LANGS = {
    "vi": "Vietnamese", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "hi": "Hindi", "es": "Spanish", "fr": "French", "de": "German",
    "pt": "Portuguese", "ru": "Russian", "ar": "Arabic", "bn": "Bengali",
    "id": "Indonesian", "ms": "Malay", "th": "Thai", "tr": "Turkish",
    "it": "Italian", "nl": "Dutch", "pl": "Polish", "uk": "Ukrainian",
    "el": "Greek", "cs": "Czech", "sv": "Swedish", "da": "Danish",
    "fi": "Finnish", "no": "Norwegian Bokmål", "hu": "Hungarian",
    "ro": "Romanian", "he": "Hebrew", "fa": "Persian", "ur": "Urdu",
    "ta": "Tamil", "te": "Telugu", "sw": "Swahili",
}
```

- [ ] **Step 1: Write the failing test**

```python
from schema import LANGUAGES
from warehouse.download_sources import DATA_SOURCES
from warehouse.ingest.wiktextract_native import KAIKKI_NATIVE_LANGS


def test_every_non_english_language_has_a_kaikki_dump_spec():
    missing = [lang for lang in LANGUAGES if lang != "en" and lang not in KAIKKI_NATIVE_LANGS]
    assert missing == []
    for lang, name in KAIKKI_NATIVE_LANGS.items():
        key = f"kaikki-{lang}"
        assert key in DATA_SOURCES
        assert name.replace(" ", "%20") in DATA_SOURCES[key]["urls"][0] or name in DATA_SOURCES[key]["urls"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wiktextract_native.py::test_every_non_english_language_has_a_kaikki_dump_spec -q`
Expected: FAIL (`KAIKKI_NATIVE_LANGS` or keys missing)

- [ ] **Step 3: Write minimal implementation**

1. Export `KAIKKI_NATIVE_LANGS` from `wiktextract_native.py` (map above).
2. In `download_sources.py`, after the existing `wiktionary` entry, loop:

```python
from warehouse.ingest.wiktextract_native import KAIKKI_NATIVE_LANGS

# inside module init, after DATA_SOURCES literal:
for _iso, _name in KAIKKI_NATIVE_LANGS.items():
    fname = f"kaikki.org-dictionary-{_name.replace(' ', '_')}.jsonl.gz"
    DATA_SOURCES[f"kaikki-{_iso}"] = {
        "filename": fname,
        "urls": [f"https://kaikki.org/dictionary/{_name}/kaikki.org-dictionary-{_name}.jsonl.gz"],
        "dest_subdir": "kaikki-native",
        "extract": False,
        "check_path": f"kaikki-native/{fname}",
    }
```

Avoid circular import: put `KAIKKI_NATIVE_LANGS` in `warehouse/ingest/kaikki_langs.py` (tiny module) if `download_sources` cannot import ingest. Prefer a new `warehouse/ingest/kaikki_langs.py` with only the dict.

3. Add `ingest_wiktextract_native` mirroring `ingest_wiktionary` flush pattern, but:
   - iterate cached files under `CACHE / "kaikki-native"`
   - `source_id = 'wiktextract-multilingual'`
   - call `native_entry_links(entry, en_index)`
   - `ensure_data_source(f"kaikki-{lang}")` per language before read

```python
def ingest_wiktextract_native(max_entries: int | None = None) -> None:
    from warehouse.download_sources import CACHE, ensure_data_source
    # build en_index exactly as ingest_wiktionary
    # for each lang in KAIKKI_NATIVE_LANGS:
    #   ensure_data_source(f"kaikki-{lang}")
    #   parse jsonl, native_entry_links, flush lemmas + sense_lemmas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wiktextract_native.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add warehouse/ingest/kaikki_langs.py warehouse/ingest/wiktextract_native.py warehouse/download_sources.py tests/test_wiktextract_native.py
git commit -m "feat(ingest): register Kaikki native dumps and write multilingual links"
```

---

### Task 3: Wikidata lexeme parser

**Files:**
- Create: `warehouse/ingest/wikidata_lexemes.py`
- Test: `tests/test_wikidata_lexemes.py`

**Interfaces:**
- Consumes: `schema.WIKT_CODE_TO_ISO`, `schema.WORDNET_POS_TO_OURS`, `warehouse.textutil`
- Produces:
  - `parse_p8814(value: str) -> tuple[int, str] | None` — `("00007846-n")` → `(7846, "noun")`
  - `wikidata_lexeme_links(entity: dict, offset_index: dict[tuple[int, str], str]) -> list[tuple[str, str, str]]`

Wikidata P8814 is WordNet 3.1 synset id (`00007846-n`). `offset_index` maps `(wn_offset, pos)` → `core.synsets.id`.

- [ ] **Step 1: Write the failing test**

```python
from warehouse.ingest.wikidata_lexemes import parse_p8814, wikidata_lexeme_links


def test_parse_p8814():
    assert parse_p8814("00007846-n") == (7846, "noun")
    assert parse_p8814("bad") is None


def test_lexeme_links_via_p8814():
    entity = {
        "type": "lexeme",
        "lemmas": {"vi": {"value": "nước"}},
        "claims": {
            "P8814": [{"mainsnak": {"datavalue": {"value": "00007846-n"}}}]
        },
    }
    offset_index = {(7846, "noun"): "water.n.01"}
    assert wikidata_lexeme_links(entity, offset_index) == [("water.n.01", "vi", "nước")]


def test_lexeme_without_wordnet_id_is_skipped():
    entity = {"type": "lexeme", "lemmas": {"vi": {"value": "nước"}}, "claims": {}}
    assert wikidata_lexeme_links(entity, {}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wikidata_lexemes.py -q`
Expected: FAIL import

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import re

from schema import WIKT_CODE_TO_ISO, WORDNET_POS_TO_OURS
from warehouse.textutil import is_usable_lemma, script_ok

_P8814 = re.compile(r"^(\d{8})-([nvasr])$")


def parse_p8814(value: str) -> tuple[int, str] | None:
    match = _P8814.match(value.strip())
    if not match:
        return None
    pos = WORDNET_POS_TO_OURS.get(match.group(2))
    if pos is None:
        return None
    return int(match.group(1)), pos


def _claim_values(entity: dict, pid: str) -> list[str]:
    out: list[str] = []
    for claim in (entity.get("claims") or {}).get(pid) or []:
        snak = claim.get("mainsnak") or {}
        val = (snak.get("datavalue") or {}).get("value")
        if isinstance(val, str):
            out.append(val)
    return out


def wikidata_lexeme_links(
    entity: dict,
    offset_index: dict[tuple[int, str], str],
) -> list[tuple[str, str, str]]:
    if entity.get("type") != "lexeme":
        return []
    synset_ids: list[str] = []
    for raw in _claim_values(entity, "P8814"):
        parsed = parse_p8814(raw)
        if parsed is None:
            continue
        synset_id = offset_index.get(parsed)
        if synset_id:
            synset_ids.append(synset_id)
    if not synset_ids:
        return []
    links: list[tuple[str, str, str]] = []
    for lang_code, lemma_obj in (entity.get("lemmas") or {}).items():
        lang = WIKT_CODE_TO_ISO.get(lang_code)
        text = lemma_obj.get("value") if isinstance(lemma_obj, dict) else None
        if lang is None or lang == "en" or not isinstance(text, str):
            continue
        lemma = text.strip()
        if not is_usable_lemma(lemma) or not script_ok(lang, lemma):
            continue
        for synset_id in synset_ids:
            links.append((synset_id, lang, lemma))
    return links
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wikidata_lexemes.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add warehouse/ingest/wikidata_lexemes.py tests/test_wikidata_lexemes.py
git commit -m "feat(ingest): map Wikidata lexemes with P8814 onto WordNet synsets"
```

---

### Task 4: Wikidata source row + ingest writer + download

**Files:**
- Modify: `sql/001_schema.sql`
- Modify: `warehouse/download_sources.py`
- Modify: `warehouse/ingest/wikidata_lexemes.py` (add `ingest_wikidata_lexemes`)
- Modify: `tests/test_wikidata_lexemes.py`

**Interfaces:**
- Consumes: `wikidata_lexeme_links`
- Produces: `ingest_wikidata_lexemes(max_entities: int | None = None) -> None`; source id `wikidata`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from warehouse.download_sources import DATA_SOURCES


def test_wikidata_lexemes_source_is_registered():
    spec = DATA_SOURCES["wikidata-lexemes"]
    assert "latest-lexemes.json.gz" in spec["filename"]
    assert spec["extract"] is False


def test_schema_sql_declares_wikidata_and_llm_sources():
    sql = Path("sql/001_schema.sql").read_text(encoding="utf-8")
    assert "('wikidata'" in sql
    assert "('llm'" in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wikidata_lexemes.py::test_wikidata_lexemes_source_is_registered tests/test_wikidata_lexemes.py::test_schema_sql_declares_wikidata_and_llm_sources -q`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Add to `DATA_SOURCES`:

```python
"wikidata-lexemes": {
    "filename": "latest-lexemes.json.gz",
    "urls": [
        "https://dumps.wikimedia.org/wikidatawiki/entities/latest-lexemes.json.gz",
    ],
    "dest_subdir": "",
    "extract": False,
    "check_path": "latest-lexemes.json.gz",
},
```

Append to `sql/001_schema.sql` sources insert:

```sql
    ('wikidata', 'Wikidata lexemes (P8814 WordNet)', 'latest', 'CC0'),
    ('llm', 'LLM gap-fill', '1', 'generated')
```

`ingest_wikidata_lexemes`: `ensure_data_source("wikidata-lexemes")`, stream gzip JSON (Wikidata dump is JSON array or JSONL — detect first non-space char; if `[` use `ijson` only if already a dependency, else line-oriented `{"type":"lexeme"` objects). Prefer: if the file is `latest-lexemes.json.gz` it is typically one entity per line after a `[` wrapper — implement a small `iter_wikidata_entities(path)` that yields dicts and unit-test it with a tiny fixture string.

Build `offset_index` from:

```sql
SELECT wn_offset, pos, id FROM core.synsets
```

Flush like wiktionary with `source_id = 'wikidata'`. Never `INSERT` into `core.synsets`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wikidata_lexemes.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sql/001_schema.sql warehouse/download_sources.py warehouse/ingest/wikidata_lexemes.py tests/test_wikidata_lexemes.py
git commit -m "feat(ingest): download and attach Wikidata lexemes without new synsets"
```

---

### Task 5: LLM gap policy (pure, no network)

**Files:**
- Create: `warehouse/ingest/llm_gaps.py`
- Test: `tests/test_llm_gaps.py`

**Interfaces:**
- Consumes: `warehouse.textutil.is_usable_lemma`, `script_ok`; `warehouse.llm.call_chat_json` (only in Task 6)
- Produces:
  - `GOLD_SOURCES: frozenset[str]`
  - `gap_cache_key(synset_id: str, lang: str) -> str`
  - `load_gap_cache(path: Path) -> dict[str, str]` mapping `"synset_id\tlang"` → lemma
  - `save_gap_cache(path: Path, cache: dict[str, str]) -> None`
  - `missing_rank_slots(ranked: set[tuple[str, str]], catalog_ids: list[str], langs: tuple[str, ...]) -> list[tuple[str, str]]`
  - `accept_llm_lemma(lang: str, text: str) -> str | None`
  - `backtranslate_ok(proposed_en: str, synset_en_lemmas: set[str]) -> bool`
  - `may_write_llm(existing_source: str | None) -> bool`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from schema import LANGUAGES
from warehouse.ingest.llm_gaps import (
    accept_llm_lemma,
    backtranslate_ok,
    load_gap_cache,
    may_write_llm,
    missing_rank_slots,
    save_gap_cache,
)


def test_missing_rank_slots_skips_filled_and_english():
    catalog = ["water.n.01", "eat.v.01"]
    ranked = {("water.n.01", "vi"), ("water.n.01", "en"), ("eat.v.01", "en")}
    missing = missing_rank_slots(ranked, catalog, ("en", "vi", "zh"))
    assert ("water.n.01", "en") not in missing
    assert ("water.n.01", "vi") not in missing
    assert ("water.n.01", "zh") in missing
    assert ("eat.v.01", "vi") in missing


def test_accept_and_backtranslate_and_gold_lock(tmp_path: Path):
    assert accept_llm_lemma("vi", "nước") == "nước"
    assert accept_llm_lemma("vi", "water") is None
    assert backtranslate_ok("water", {"water", "H2O"})
    assert not backtranslate_ok("chair", {"water"})
    assert may_write_llm(None)
    assert not may_write_llm("omw-1.4")
    path = tmp_path / "gaps.json"
    save_gap_cache(path, {"water.n.01\tvi": "nước"})
    assert load_gap_cache(path)["water.n.01\tvi"] == "nước"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_llm_gaps.py -q`
Expected: FAIL import

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import json
from pathlib import Path

from warehouse.textutil import is_usable_lemma, normalize, script_ok

GOLD_SOURCES = frozenset({
    "wordnet", "omw-1.4", "wiktionary", "wiktextract",
    "wiktextract-multilingual", "wikidata",
})
GAP_CACHE_FILE = Path(__file__).resolve().parents[1] / "llm_gap_cache.json"


def gap_cache_key(synset_id: str, lang: str) -> str:
    return f"{synset_id}\t{lang}"


def load_gap_cache(path: Path = GAP_CACHE_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): str(v) for k, v in raw.items() if v}


def save_gap_cache(path: Path, cache: dict[str, str]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def missing_rank_slots(
    ranked: set[tuple[str, str]],
    catalog_ids: list[str],
    langs: tuple[str, ...],
) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for synset_id in catalog_ids:
        for lang in langs:
            if lang == "en":
                continue
            if (synset_id, lang) not in ranked:
                missing.append((synset_id, lang))
    return missing


def accept_llm_lemma(lang: str, text: str) -> str | None:
    lemma = text.strip()
    if not is_usable_lemma(lemma) or not script_ok(lang, lemma):
        return None
    return lemma


def backtranslate_ok(proposed_en: str, synset_en_lemmas: set[str]) -> bool:
    folded = {normalize(item) for item in synset_en_lemmas}
    return normalize(proposed_en) in folded


def may_write_llm(existing_source: str | None) -> bool:
    return existing_source is None or existing_source not in GOLD_SOURCES
```

English is never an LLM gap (`lang == "en"` skipped): the pivot already has 12,000 terms.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_llm_gaps.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add warehouse/ingest/llm_gaps.py tests/test_llm_gaps.py
git commit -m "feat(ingest): add LLM gap-fill policy, cache, and gold lock"
```

---

### Task 6: LLM propose + ingest job

**Files:**
- Modify: `warehouse/ingest/llm_gaps.py`
- Modify: `tests/test_llm_gaps.py`

**Interfaces:**
- Consumes: `warehouse.llm.call_chat_json`, `JobContext` (optional)
- Produces:
  - `GAP_SYSTEM_PROMPT: str`
  - `propose_lemma(synset_id: str, pos: str, definition_en: str, en_lemmas: list[str], lang: str, candidates: list[str], call_json=call_chat_json) -> str | None`
  - `ingest_llm_gaps(limit: int | None = None, job: JobContext | None = None) -> None`

Prompt must request JSON `{"lemma": "<text>", "back_en": "<english lemma>"}`.

- [ ] **Step 1: Write the failing test**

```python
from warehouse.ingest.llm_gaps import propose_lemma


def test_propose_lemma_accepts_valid_roundtrip():
    def fake_call(system, user, **kwargs):
        assert "water.n.01" in user
        return {"lemma": "nước", "back_en": "water"}

    assert propose_lemma(
        "water.n.01", "noun", "a liquid", ["water"], "vi", [], call_json=fake_call
    ) == "nước"


def test_propose_lemma_rejects_bad_backtranslate_then_none_on_second_fail():
    calls = {"n": 0}

    def fake_call(system, user, **kwargs):
        calls["n"] += 1
        return {"lemma": "nước", "back_en": "chair"}

    assert propose_lemma(
        "water.n.01", "noun", "a liquid", ["water"], "vi", [], call_json=fake_call
    ) is None
    assert calls["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_llm_gaps.py::test_propose_lemma_accepts_valid_roundtrip tests/test_llm_gaps.py::test_propose_lemma_rejects_bad_backtranslate_then_none_on_second_fail -q`
Expected: FAIL `propose_lemma` not defined

- [ ] **Step 3: Write minimal implementation**

```python
GAP_SYSTEM_PROMPT = """You are a lexicographer. Given one WordNet synset, return the single most
natural learner headword in the requested language for THIS sense only.
Return JSON only: {"lemma": "<native lemma>", "back_en": "<English lemma of that sense>"}.
back_en must be one of the provided English lemmas."""


def propose_lemma(
    synset_id: str,
    pos: str,
    definition_en: str,
    en_lemmas: list[str],
    lang: str,
    candidates: list[str],
    call_json=None,
) -> str | None:
    from warehouse.llm import call_chat_json
    caller = call_json or call_chat_json
    user = "\n".join([
        f"Synset: {synset_id}",
        f"POS: {pos}",
        f"Definition: {definition_en}",
        f"English lemmas: {', '.join(en_lemmas)}",
        f"Language: {lang}",
        f"Candidates: {', '.join(candidates) if candidates else '(none)'}",
    ])
    for _ in range(2):
        try:
            payload = caller(GAP_SYSTEM_PROMPT, user)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        lemma = accept_llm_lemma(lang, str(payload.get("lemma") or ""))
        back_en = str(payload.get("back_en") or "")
        if lemma and backtranslate_ok(back_en, set(en_lemmas)):
            return lemma
    return None
```

`ingest_llm_gaps`:

1. Load catalog synset ids from `core.concept_ranks` distinct `synset_id` where English exists (the 12k set).
2. `ranked = {(synset_id, lang) from core.concept_ranks}`.
3. `slots = missing_rank_slots(...)`; if `limit`, slice.
4. For each slot: if cache hit and `accept_llm_lemma` ok → use it; else `propose_lemma`; on success `save_gap_cache` every 50.
5. Insert lemma + `sense_lemmas` with `source_id='llm'` only when `may_write_llm(existing_source)`.
6. After inserts, caller will run `compute_ranks(12000)` (Task 7 CLI), not inside the unit test.

If `job` is set: `job.progress(i, total)`, `job.log(...)`, stop when `job.cancelled()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_llm_gaps.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add warehouse/ingest/llm_gaps.py tests/test_llm_gaps.py
git commit -m "feat(ingest): propose LLM lemmas with required back-translate"
```

---

### Task 7: CLI and console jobs

**Files:**
- Modify: `warehouse/cli.py`
- Modify: `warehouse/web.py`

**Interfaces:**
- Consumes: `ingest_wiktextract_native`, `ingest_wikidata_lexemes`, `ingest_llm_gaps`, `compute_ranks`
- Produces: CLI `--only` choices `wiktextract-native`, `wikidata`, `llm-gaps`; OPS names `wiktextract-native`, `wikidata`, `llm-gaps`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_llm_gaps.py` (or a tiny `tests/test_cli_ops.py`):

```python
from warehouse.cli import main
from warehouse.web import OPS


def test_ops_and_cli_advertise_new_jobs():
    names = {item[0] for item in OPS}
    assert {"wiktextract-native", "wikidata", "llm-gaps"} <= names
```

Do not invoke `main()` (it requires argparse dest). Only assert the parser choices by importing the module after wiring.

Better: extract allowed ingest-only names:

```python
# warehouse/cli.py
INGEST_ONLY = (
    "wordfreq", "wordnet", "omw", "wiktionary", "readings",
    "wiktextract-native", "wikidata", "llm-gaps",
)
```

```python
from warehouse.cli import INGEST_ONLY

def test_ingest_only_includes_coverage_pipeline():
    assert "wiktextract-native" in INGEST_ONLY
    assert "wikidata" in INGEST_ONLY
    assert "llm-gaps" in INGEST_ONLY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_llm_gaps.py::test_ops_and_cli_advertise_new_jobs tests/test_llm_gaps.py::test_ingest_only_includes_coverage_pipeline -q`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`cli.py`:

```python
INGEST_ONLY = (
    "wordfreq", "wordnet", "omw", "wiktionary", "readings",
    "wiktextract-native", "wikidata", "llm-gaps",
)
# ingest.add_argument("--only", choices=INGEST_ONLY, ...)
# if only in (None, "wiktextract-native"): ingest_wiktextract_native(max_entries=args.limit)
# if only in (None, "wikidata"): ingest_wikidata_lexemes(max_entities=args.limit)
# if only == "llm-gaps": ingest_llm_gaps(limit=args.limit); compute_ranks(args.limit or 12000)
```

Do **not** run native/wikidata/llm on a bare `ingest` with no `--only` (full ingest would download tens of GB). Default `ingest` stays wordfreq+wordnet+omw+wiktionary+readings.

`web.py` OPS append:

```python
    ("wiktextract-native", "Ingest native Wiktionary", "Long. Kaikki per-language dumps."),
    ("wikidata", "Ingest Wikidata lexemes", "Long. P8814 only."),
    ("llm-gaps", "LLM fill empty ranks", "Needs LLM config. Resumable."),
```

`_job` branches call the three ingest functions; `llm-gaps` then `compute_ranks(12000)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests/test_wiktextract_native.py tests/test_wikidata_lexemes.py tests/test_llm_gaps.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add warehouse/cli.py warehouse/web.py tests/test_llm_gaps.py
git commit -m "feat(ops): expose native, Wikidata, and LLM gap jobs"
```

---

### Task 8: Export coverage gate

**Files:**
- Create: `tests/test_coverage_gate.py`
- Modify: `warehouse/export_sqlite.py` only if a helper is needed (prefer keep tests on `write_catalog_sqlite`)

**Interfaces:**
- Consumes: `schema.LANGUAGES`, `warehouse.export_sqlite.write_catalog_sqlite`
- Produces: `coverage_counts(conn) -> dict[str, int]` can live in the test file

- [ ] **Step 1: Write the failing test**

```python
import sqlite3
from schema import LANGUAGES
from warehouse.export_sqlite import write_catalog_sqlite


def test_full_matrix_export_has_every_language():
    langs = list(LANGUAGES)
    concepts = []
    for i in range(3):
        terms = {lang: {"text": f"w{i}-{lang}" if lang != "zh" else "水", "rank": i + 1, "meaning": "m"} for lang in langs}
        terms["zh"]["text"] = "水"
        terms["ja"]["text"] = "水"
        terms["ko"]["text"] = "물"
        terms["ar"]["text"] = "ماء"
        terms["he"]["text"] = "מים"
        terms["hi"]["text"] = "पानी"
        terms["bn"]["text"] = "জল"
        terms["ta"]["text"] = "நீர்"
        terms["te"]["text"] = "నీరు"
        terms["th"]["text"] = "น้ำ"
        terms["ru"]["text"] = "вода"
        terms["uk"]["text"] = "вода"
        terms["el"]["text"] = "νερό"
        terms["vi"]["text"] = "nước"
        concepts.append({"id": f"c{i}.n.01", "pos": "noun", "meaning": "x", "terms": terms})
    dest = write_catalog_sqlite(
        {"version": 1, "count": 3, "topN": 3, "languages": langs, "concepts": concepts},
        __import__("pathlib").Path("/tmp/coverage-gate.db"),
    )
    conn = sqlite3.connect(dest)
    counts = dict(conn.execute("SELECT lang, COUNT(*) FROM terms GROUP BY lang"))
    conn.close()
    dest.unlink(missing_ok=True)
    assert set(counts) == set(langs)
    assert all(n == 3 for n in counts.values())
```

Note: `write_catalog_sqlite` currently inserts `meaning` only if the INSERT includes it — check the live function. Today it inserts `(concept_id, lang, text, rank, readings)` and **drops `meaning`**. Do **not** change that in this task unless a test already requires meaning. Coverage gate is term counts only. Release gate for meaning stays a SQL check after gloss attach:

```sql
SELECT COUNT(*) FROM terms WHERE meaning IS NULL OR meaning = '';
```

If the shipped `write_catalog_sqlite` still omits meaning, add a follow-up assertion only after `build_pedagogical_core` is used for the real export. Do not expand schema here.

- [ ] **Step 2: Run test to verify it fails**

If the test is written against current `write_catalog_sqlite` and the catalog is complete, it may **PASS immediately**. That is acceptable: the gate documents the release invariant. If script_ok is not applied at export (it is not), the dummy CJK/Arabic texts are only for realism.

If it fails on UNIQUE/insert, fix the fixture.

- [ ] **Step 3: No production change unless the test reveals export drops langs with rank < 1**

`write_catalog_sqlite` skips `rank < 1`. Fixture uses rank 1..3.

- [ ] **Step 4: Run full warehouse tests**

Run: `/Users/admin/Documents/big-data/.venv/bin/python -m pytest tests -q`
Expected: all PASS (including existing `test_readings.py`, `test_export_sqlite.py`)

- [ ] **Step 5: Commit**

```bash
git add tests/test_coverage_gate.py
git commit -m "test: gate exported catalog language matrix coverage"
```

---

### Task 9: Operator runbook (no new code unless a hole appears)

**Files:**
- Modify: `docs/superpowers/specs/2026-08-19-full-coverage-lexicon-pipeline-design.md` only if a command in the spec is wrong; otherwise add a short section to `README.md` **only if the repo already documents ingest commands**. If README has an ingest section, append the three new commands. If not, skip README (YAGNI).

Production sequence (run on the machine with Postgres + `.env` LLM):

```bash
# 1) migrate picks up wikidata + llm source rows
python -m warehouse migrate

# 2) native dumps (large). Use --limit for smoke.
python -m warehouse ingest --only wiktextract-native
python -m warehouse ingest --only wikidata

# 3) re-rank so new lemmas can become headwords
python -m warehouse rank --top-n 12000

# 4) fill remaining empty (synset, lang) cells
python -m warehouse ingest --only llm-gaps

# 5) readings + gloss + sqlite
python -m warehouse ingest --only readings
python -m warehouse export-sqlite --top-n 12000

# 6) release check
python - <<'PY'
import sqlite3
from schema import LANGUAGES
c = sqlite3.connect("out/lexicon-core.db")
rows = dict(c.execute("SELECT lang, COUNT(*) FROM terms GROUP BY lang"))
assert all(rows.get(lang) == 12000 for lang in LANGUAGES), rows
print("coverage ok", len(rows), sum(rows.values()))
PY

# 7) copy seed into the extension (separate repo)
# cp out/lexicon-core.db.gz ../Fumihiko/livecode-extension/frontend-extension/public/vocabulary/
```

- [ ] **Step 1:** Confirm README ingest docs exist; update only if they list `--only` values.
- [ ] **Step 2:** Do not run the full GB downloads in CI.
- [ ] **Step 3:** Commit README only if it changed.

```bash
git add README.md
git commit -m "docs: document full-coverage ingest commands"
```

---

## Self-review

1. **Spec coverage**
   - Tầng 1 Wiktextract native → Tasks 1–2
   - Tầng 1 Wikidata → Tasks 3–4
   - Tầng 2 rank unchanged → Task 7 (`llm-gaps` calls `compute_ranks`) + Task 9
   - Tầng 3 LLM + cache + gold lock + back-translate + JobContext → Tasks 5–6
   - Tầng 4 readings/gloss/export → Task 9 (existing commands)
   - Never new synsets / never invent IPA / frontend schema unchanged → Global Constraints + Task 3 skip + Task 8 no schema change
   - Release gate 12k × 35 → Task 8 + Task 9 SQL check

2. **Placeholder scan:** none. Parsers, prompts, URLs, source ids, CLI names are explicit.

3. **Type consistency:** `native_entry_links` / `wikidata_lexeme_links` both return `list[tuple[str, str, str]]` = `(synset_id, lang, lemma)`. Cache key `synset_id\tlang`. Source ids: `wiktextract-multilingual`, `wikidata`, `llm`.
