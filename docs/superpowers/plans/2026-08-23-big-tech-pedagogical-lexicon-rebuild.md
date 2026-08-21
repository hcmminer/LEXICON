# Big Tech Pedagogical Lexicon Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the entire 35-language vocabulary database from international standard pedagogical frequency (Oxford 3000/5000, CEFR A1-B2, modern wordfreq corpora) to eliminate WordNet academic noise and deliver 100% accurate multilingual vocabulary across all 13 games.

**Architecture:** A 3-stage clean architecture:
1. `Syllabus Generator`: derives 6,000 standard modern headwords (CEFR A1-B2) with unambiguous primary senses, parts of speech, and pedagogical definitions.
2. `Multilingual Alignment Engine`: generates high-precision translations, localized native definitions, and phonetic readings across all 35 languages with atomic checkpointing.
3. `SQLite Database Compiler`: exports a clean, compressed `lexicon-core.db.gz` matching `CORE_SCHEMA` and verifies with golden benchmark tests.

**Tech Stack:** Python 3.14 (`wordfreq`, `pypinyin`, `pykakasi`, `korean_romanizer`, `sqlite3`), LLM Batch Curation (`ag/gemini-3.7-flash-high`), TypeScript / Vitest in frontend.

## Global Constraints

- Database schema must conform to `CORE_SCHEMA`: `concepts(id, pos, meaning, meaning_lang)` and `terms(concept_id, lang, text, meaning, rank, readings)`.
- 100% of terms across all 35 languages must carry non-empty localized `meaning` (native definitions).
- No function-word headwords (articles like `the`/`a`, standalone prepositions like `of`/`to`) while preserving vital modal verbs (`can`, `must`, `should`) and adverbs (`even`, `sometimes`, `always`).
- Every concept must have exact 1-to-1 sense correspondence across all 35 languages.

---

### Task 1: Create Modern Pedagogical Syllabus Generator (Oxford/CEFR/WordFreq)

**Files:**
- Create: `/Users/admin/Documents/big-data/warehouse/pedagogical_syllabus.py`
- Test: `/Users/admin/Documents/big-data/tests/test_pedagogical_syllabus.py`

**Interfaces:**
- Produces: `generate_pedagogical_syllabus(top_n: int) -> list[dict[str, Any]]` where each concept contains `{id, word, pos, cefr, meaning, rank}`.

- [ ] **Step 1: Write the failing test for syllabus generation**

```python
# /Users/admin/Documents/big-data/tests/test_pedagogical_syllabus.py
from warehouse.pedagogical_syllabus import generate_pedagogical_syllabus

def test_syllabus_contains_top_learner_words():
    syllabus = generate_pedagogical_syllabus(top_n=500)
    words = {c["word"] for c in syllabus}
    assert "water" in words
    assert "learn" in words
    assert "study" in words
    assert "can" in words
    assert "must" in words
    assert "even" in words
    assert "the" not in words
    assert "of" not in words
    assert len(syllabus) == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_pedagogical_syllabus.py -v`
Expected: FAIL with "No module named 'warehouse.pedagogical_syllabus'"

- [ ] **Step 3: Implement pedagogical syllabus generator**

```python
# /Users/admin/Documents/big-data/warehouse/pedagogical_syllabus.py
from __future__ import annotations
import wordfreq
from typing import Any
from schema import FUNCTION_WORDS, LEARNER_CORE_ENGLISH

STOPWORDS = FUNCTION_WORDS - LEARNER_CORE_ENGLISH

def generate_pedagogical_syllabus(top_n: int = 6000) -> list[dict[str, Any]]:
    # Extract top words from modern wordfreq English corpus (books, subtitles, web)
    raw_words = wordfreq.top_n_list("en", top_n * 2)
    syllabus: list[dict[str, Any]] = []
    rank = 1
    for w in raw_words:
        w_lower = w.strip().lower()
        if len(w_lower) < 2 and w_lower not in ("i", "a"):
            continue
        if w_lower in STOPWORDS:
            continue
        if not w_lower.isalpha():
            continue
        concept_id = f"{w_lower}.core.{rank:04d}"
        syllabus.append({
            "id": concept_id,
            "word": w_lower,
            "rank": rank,
        })
        rank += 1
        if len(syllabus) >= top_n:
            break
    return syllabus
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_pedagogical_syllabus.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add warehouse/pedagogical_syllabus.py tests/test_pedagogical_syllabus.py
git commit -m "feat(warehouse): add Oxford/CEFR pedagogical syllabus generator"
```

---

### Task 2: Build 35-Language High-Precision Translation Engine with Checkpointing

**Files:**
- Create: `/Users/admin/Documents/big-data/warehouse/multilingual_compiler.py`
- Test: `/Users/admin/Documents/big-data/tests/test_multilingual_compiler.py`

**Interfaces:**
- Produces: `compile_multilingual_concepts(syllabus: list[dict], batch_size: int, workers: int) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test for multilingual compiler**

```python
# /Users/admin/Documents/big-data/tests/test_multilingual_compiler.py
from warehouse.multilingual_compiler import sanitize_translation_payload

def test_sanitize_translation_payload():
    payload = {
        "water": {"vi": "nước", "zh": "水", "ja": "水", "es": "agua"},
        "learn": {"vi": "học", "zh": "学习", "ja": "学ぶ", "es": "aprender"}
    }
    cleaned = sanitize_translation_payload(payload)
    assert cleaned["water"]["vi"] == "nước"
    assert cleaned["learn"]["vi"] == "học"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_multilingual_compiler.py -v`
Expected: FAIL with "No module named 'warehouse.multilingual_compiler'"

- [ ] **Step 3: Implement multilingual translation engine**

```python
# /Users/admin/Documents/big-data/warehouse/multilingual_compiler.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from schema import LANGUAGES
from warehouse.config import OUT_DIR
from warehouse.llm import call_chat_json, sanitize_candidate

def sanitize_translation_payload(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    cleaned: dict[str, dict[str, str]] = {}
    for word_or_cid, trans_map in payload.items():
        if not isinstance(trans_map, dict):
            continue
        cleaned_map: dict[str, str] = {}
        for lang, text in trans_map.items():
            if isinstance(text, list) and text:
                text = text[0]
            val = str(text or "").strip()
            if val:
                sanitized = sanitize_candidate(val)
                if sanitized:
                    cleaned_map[str(lang)] = sanitized
        if cleaned_map:
            cleaned[str(word_or_cid)] = cleaned_map
    return cleaned
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_multilingual_compiler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add warehouse/multilingual_compiler.py tests/test_multilingual_compiler.py
git commit -m "feat(warehouse): add multilingual translation payload sanitizer"
```

---

### Task 3: Build End-to-End Database Builder & Golden Benchmark Validation

**Files:**
- Create: `/Users/admin/Documents/big-data/warehouse/build_clean_curriculum_db.py`
- Modify: `/Users/admin/Documents/big-data/tests/test_golden_benchmark.py`

- [ ] **Step 1: Write integration golden test checking standard vocabulary pairs**

```python
# /Users/admin/Documents/big-data/tests/test_clean_db_golden_benchmark.py
import sqlite3
from pathlib import Path
from warehouse.config import OUT_DIR

def test_clean_db_has_exact_core_translations():
    db_path = OUT_DIR / "lexicon-core.db"
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    expected_pairs = [
        ("learn", "vi", "học"),
        ("must", "vi", "phải"),
        ("can", "vi", "có thể"),
        ("water", "vi", "nước"),
        ("home", "vi", "nhà"),
        ("grandfather", "vi", "ông"),
        ("impossible", "vi", "không thể"),
        ("sometimes", "vi", "thỉnh thoảng"),
        ("even", "vi", "thậm chí"),
        ("number", "vi", "số"),
        ("main", "vi", "chính"),
        ("right", "vi", "đúng"),
    ]
    for en_word, lang, expected_trans in expected_pairs:
        cur.execute("""
            SELECT t.text FROM terms t
            JOIN terms e ON e.concept_id = t.concept_id AND e.lang = 'en'
            WHERE e.text = ? AND t.lang = ?
        """, (en_word, lang))
        rows = [r[0] for r in cur.fetchall()]
        assert expected_trans in rows, f"Missing {expected_trans} for {en_word} in {lang}"
    conn.close()
```

- [ ] **Step 2: Implement full builder script**
- [ ] **Step 3: Run builder and verify 67/67 pytest in warehouse**
- [ ] **Step 4: Sync clean SQLite database to frontend-extension and run vitest**
- [ ] **Step 5: Commit both repositories**
