#!/usr/bin/env python3
"""
warehouse/build_pedagogical_core.py

Generates clean, standard, high-frequency pedagogical vocabulary lists
(Oxford 3000/5000, CEFR A1-B2, HSK 1-6, JLPT N5-N1 style) for all supported languages.

Eliminates academic WordNet micro-synset noise (no tribal language names, no obscure archaic senses).
"""

from __future__ import annotations

import gzip
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from schema import LANGUAGES, SCHEMA_VERSION, empty_envelope
from warehouse.config import OUT_DIR
from warehouse.gloss_generator import load_gloss_cache
from warehouse.build_readings import readings_for
from warehouse.textutil import is_function_word, is_usable_lemma

OVERRIDE_PATH = Path(__file__).parent / "curated_overrides.json"


def load_curated_overrides() -> dict[str, dict[str, str]]:
    if OVERRIDE_PATH.exists():
        try:
            return json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def build_pedagogical_catalog(top_n: int = 6000, pivot: str | None = None) -> dict[str, Any]:
    """
    Builds a clean pedagogical vocabulary catalog from verified core lemmas and primary definitions.
    """
    raw_catalog_path = OUT_DIR / "core_vocabulary.json.gz"
    if not raw_catalog_path.exists():
        raw_catalog_path = Path(__file__).resolve().parents[1] / "out" / "core_vocabulary.json.gz"

    with gzip.open(raw_catalog_path, "rt", encoding="utf-8") as f:
        raw = json.load(f)

    overrides = load_curated_overrides()
    gloss_cache = load_gloss_cache()
    cleaned_concepts: list[dict[str, Any]] = []

    # Banned obscure / archaic / specialized sense indicators
    BANNED_MEANING_SUBSTRINGS = (
        "algonquian language",
        "member of an algonquian",
        "former capital",
        "genus of",
        "family of",
        "order of",
        "suborder of",
        "archaic",
        "historical region",
        "monetary unit of",
    )

    for concept in raw.get("concepts", []):
        cid = concept.get("id", "")
        meaning = concept.get("meaning", "").lower()
        
        # Skip obscure scientific / tribal / archaic micro-synsets
        if any(b in meaning for b in BANNED_MEANING_SUBSTRINGS):
            continue

        # Prioritize concepts that have verified localized glosses in cache
        if cid not in gloss_cache:
            continue

        # Clean terms
        terms = concept.get("terms", {})
        if not terms or "en" not in terms:
            continue

        # Apply overrides if available
        if cid in overrides:
            for lang, text in overrides[cid].items():
                if lang in terms:
                    terms[lang]["text"] = text
                else:
                    terms[lang] = {"text": text, "rank": 9999}

        terms = {
            lang: term_obj
            for lang, term_obj in terms.items()
            if is_usable_lemma(str(term_obj.get("text") or ""))
            and not is_function_word(lang, str(term_obj.get("text") or ""))
        }
        if "en" not in terms:
            continue

        # Apply localized meaning / gloss if present in cache, otherwise omit
        for lang, term_obj in terms.items():
            if cid in gloss_cache and lang in gloss_cache[cid]:
                term_obj["meaning"] = gloss_cache[cid][lang]
            generated = readings_for(lang, str(term_obj.get("text") or ""))
            if generated:
                term_obj["readings"] = generated
            elif "readings" in term_obj:
                del term_obj["readings"]

        concept["terms"] = terms
        cleaned_concepts.append(concept)
        if len(cleaned_concepts) >= top_n:
            break

    # Re-rank ranks continuously 1..N per language in union or pivot
    by_lang: dict[str, list[dict[str, Any]]] = {}
    for concept in cleaned_concepts:
        for lang, term in concept.get("terms", {}).items():
            by_lang.setdefault(lang, []).append(term)
    for lang, terms_list in by_lang.items():
        terms_list.sort(key=lambda t: (t.get("rank", 99999), t.get("text", "")))
        for r_idx, t in enumerate(terms_list, start=1):
            t["rank"] = r_idx

    # If pivot language is specified, re-rank according to pivot terms
    if pivot:
        pivoted = [c for c in cleaned_concepts if pivot in c.get("terms", {})]
        pivoted.sort(key=lambda c: c["terms"][pivot]["rank"])
        cleaned_concepts = pivoted[:top_n]
    else:
        cleaned_concepts.sort(key=lambda c: (c["terms"]["en"]["rank"], c["id"]))

    catalog = empty_envelope(len(cleaned_concepts), top_n, pivot)
    catalog["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    catalog["version"] = SCHEMA_VERSION
    catalog["languages"] = list(LANGUAGES)
    catalog["concepts"] = cleaned_concepts
    return catalog


def export_pedagogical_assets() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("🚀 Building clean pedagogical Tier-1 catalog (Top 3k, 6k, 9k, 12k)...")
    
    # 1. Export standard Union catalog (Top 12000)
    union_catalog = build_pedagogical_catalog(top_n=12000)
    union_out = OUT_DIR / "core_vocabulary.json.gz"
    payload = json.dumps(union_catalog, ensure_ascii=False, indent=2)
    with gzip.open(union_out, "wt", encoding="utf-8") as f:
        f.write(payload)
    print(f"✅ Exported Union Catalog ({len(union_catalog['concepts'])} concepts) -> {union_out}")

    # 2. Export 35 language packs for 3000, 6000, 9000, 12000 goals
    for n in (3000, 6000, 9000, 12000):
        for lang in LANGUAGES:
            p_cat = build_pedagogical_catalog(top_n=n, pivot=lang)
            p_out = OUT_DIR / f"core_vocabulary.{lang}-{n}.json.gz"
            with gzip.open(p_out, "wt", encoding="utf-8") as f:
                json.dump(p_cat, f, ensure_ascii=False)
        print(f"✅ Exported {len(LANGUAGES)} packs for Top-{n}")


if __name__ == "__main__":
    export_pedagogical_assets()
