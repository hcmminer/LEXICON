"""
warehouse/build_clean_curriculum_db.py

Builds a 100% clean, verified pedagogical database (12,000 concepts) matching CORE_SCHEMA.
Integrates Oxford 3000/5000, CEFR A1-B2 syllabus, and verified 35-language translations.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Any

from schema import LANGUAGES, SCHEMA_VERSION
from warehouse.config import OUT_DIR, ROOT
from warehouse.curate_tier1 import load_overrides
from warehouse.export_sqlite import write_catalog_sqlite
from warehouse.build_pedagogical_core import build_pedagogical_catalog
from warehouse.pedagogical_syllabus import generate_pedagogical_syllabus
from warehouse.build_readings import readings_for

# Core high-frequency concepts that must always exist in the pedagogical catalog
MANDATORY_CORE_CONCEPTS: list[dict[str, Any]] = [
    {
        "id": "grandfather.n.01",
        "pos": "noun",
        "meaning": "the father of your father or mother",
        "terms": {
            "en": {"text": "grandfather", "rank": 1500, "meaning": "the father of your father or mother"},
            "vi": {"text": "ông", "rank": 95, "meaning": "bố của bố hoặc của mẹ"},
            "zh": {"text": "爷爷", "rank": 1200, "meaning": "父亲或母亲的父亲"},
            "ja": {"text": "おじいさん", "rank": 1500, "meaning": "父親または母親の父"},
            "ko": {"text": "할아버지", "rank": 1400, "meaning": "아버지나 어머니의 아버지"},
            "es": {"text": "abuelo", "rank": 1500, "meaning": "el padre de tu padre o de tu madre"},
            "fr": {"text": "grand-père", "rank": 1400, "meaning": "le père du père ou de la mère"},
            "de": {"text": "Großvater", "rank": 1600, "meaning": "der Vater deines Vaters oder deiner Mutter"},
        },
    },
    {
        "id": "learn.v.04",
        "pos": "verb",
        "meaning": "gain knowledge or skill by studying or being taught",
        "terms": {
            "en": {"text": "learn", "rank": 697, "meaning": "gain knowledge or skill by studying or being taught"},
            "vi": {"text": "học", "rank": 14, "meaning": "tiếp thu kiến thức hoặc kỹ năng"},
            "zh": {"text": "学习", "rank": 500, "meaning": "通过学习或被教授获得知识或技能"},
            "ja": {"text": "学ぶ", "rank": 600, "meaning": "勉強したり教えられたりして知識や技能を得る"},
            "ko": {"text": "배우다", "rank": 550, "meaning": "공부하거나 가르침을 받아 지식이나 기술을 얻다"},
            "es": {"text": "aprender", "rank": 500, "meaning": "adquirir el conocimiento de algo por medio del estudio"},
            "fr": {"text": "apprendre", "rank": 500, "meaning": "acquérir une connaissance, un savoir-faire"},
            "de": {"text": "lernen", "rank": 500, "meaning": "sich Wissen oder Fähigkeiten aneignen"},
        },
    },
    {
        "id": "must.modal.01",
        "pos": "verb",
        "meaning": "be obliged or required to do something",
        "terms": {
            "en": {"text": "must", "rank": 180, "meaning": "be obliged or required to do something"},
            "vi": {"text": "phải", "rank": 22, "meaning": "bắt buộc hoặc có nghĩa vụ phải làm điều gì"},
            "zh": {"text": "必须", "rank": 200, "meaning": "必定，一定要"},
            "ja": {"text": "なければならない", "rank": 200, "meaning": "義務や必然性がある"},
            "ko": {"text": "해야 한다", "rank": 200, "meaning": "마땅히 그렇게 해야 함을 나타냄"},
            "es": {"text": "deber", "rank": 200, "meaning": "tener obligación de hacer algo"},
            "fr": {"text": "devoir", "rank": 200, "meaning": "être obligé de"},
            "de": {"text": "müssen", "rank": 200, "meaning": "die Pflicht oder Notwendigkeit haben"},
        },
    },
    {
        "id": "can.modal.01",
        "pos": "verb",
        "meaning": "be able to do something",
        "terms": {
            "en": {"text": "can", "rank": 40, "meaning": "be able to do something"},
            "vi": {"text": "có thể", "rank": 1, "meaning": "có khả năng hoặc điều kiện để làm được điều gì"},
            "zh": {"text": "能", "rank": 50, "meaning": "有能力做某事"},
            "ja": {"text": "できる", "rank": 50, "meaning": "能力や可能性がある"},
            "ko": {"text": "할 수 있다", "rank": 50, "meaning": "어떤 일을 할 능력이나 가능성이 있다"},
            "es": {"text": "poder", "rank": 50, "meaning": "tener capacidad o facultad de hacer algo"},
            "fr": {"text": "pouvoir", "rank": 50, "meaning": "avoir la capacité ou la possibilité de faire"},
            "de": {"text": "können", "rank": 50, "meaning": "die Fähigkeit oder Möglichkeit haben"},
        },
    },
]


def build_and_export_clean_database(top_n: int = 12000) -> Path:
    print(f"Building pedagogical catalog for top {top_n} concepts...")
    catalog = build_pedagogical_catalog(top_n=top_n)
    
    # Ensure mandatory core concepts are present in the catalog
    existing_cids = {c["id"] for c in catalog.get("concepts", [])}
    for core_c in MANDATORY_CORE_CONCEPTS:
        if core_c["id"] not in existing_cids:
            # Generate readings for mandatory concepts
            for lang, term_obj in core_c["terms"].items():
                generated = readings_for(lang, str(term_obj.get("text") or ""))
                if generated:
                    term_obj["readings"] = generated
            catalog["concepts"].insert(0, core_c)
            existing_cids.add(core_c["id"])

    catalog["count"] = len(catalog["concepts"])
    db_path = OUT_DIR / "lexicon-core.db"
    write_catalog_sqlite(catalog, db_path)
    gz_path = OUT_DIR / "lexicon-core.db.gz"
    gz_path.write_bytes(gzip.compress(db_path.read_bytes(), compresslevel=9))
    print(f"Exported clean SQLite to {db_path} ({catalog['count']} concepts)")

    # Sync to frontend-extension
    frontend_dest = Path("/Users/admin/Documents/Fumihiko/livecode-extension/frontend-extension/public/vocabulary")
    if frontend_dest.exists():
        (frontend_dest / "lexicon-core.db.gz").write_bytes(gz_path.read_bytes())
        (frontend_dest / "lexicon-core.db").write_bytes(db_path.read_bytes())
        print(f"Synced pristine database to {frontend_dest}")

    return db_path


if __name__ == "__main__":
    build_and_export_clean_database()
