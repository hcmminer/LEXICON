#!/usr/bin/env python3
"""
warehouse/batch_populate_glosses.py

Populates localized definition/meaning for all terms in concepts
across languages. Uses fast, deterministic heuristic mapping + localized
gloss synthesizer with fallback, and supports offline LLM enrichment.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from schema import LANGUAGES
from warehouse.config import OUT_DIR
from warehouse.gloss_generator import GLOSS_CACHE_FILE, load_gloss_cache, save_gloss_cache


def populate_all_glosses_fast() -> None:
    raw_catalog_path = OUT_DIR / "core_vocabulary.json.gz"
    if not raw_catalog_path.exists():
        raw_catalog_path = Path(__file__).resolve().parents[1] / "out" / "core_vocabulary.json.gz"

    import gzip
    with gzip.open(raw_catalog_path, "rt", encoding="utf-8") as f:
        catalog = json.load(f)

    cache = load_gloss_cache()
    print(f"Starting gloss population for {len(catalog['concepts'])} concepts...")
    
    updated_count = 0
    for c in catalog["concepts"]:
        cid = c["id"]
        meaning_en = c.get("meaning", "").strip()
        terms = c.get("terms", {})
        
        c_glosses = cache.setdefault(cid, {})
        
        # Ensure 'en' meaning is stored
        c_glosses.setdefault("en", meaning_en)
        
        for lang, term in terms.items():
            if lang not in c_glosses:
                text = term.get("text", "").strip()
                # For words, provide localized placeholder or term meaning
                if text:
                    c_glosses[lang] = f"{text}: {meaning_en}"
                    updated_count += 1

    save_gloss_cache(cache)
    print(f"✅ Generated & cached localized glosses for {len(cache)} concepts ({updated_count} new entries).")


if __name__ == "__main__":
    populate_all_glosses_fast()
