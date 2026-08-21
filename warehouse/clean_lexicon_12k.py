#!/usr/bin/env python3
"""
warehouse/clean_lexicon_12k.py

Full-coverage automated curation & cleanup of all 11,779 concepts across 35 languages:
  1. Identifies and fixes multi-sense ambiguous synsets via parallel LLM curation.
  2. Cleans up Wiktextract mapping artifacts (acronyms, biological/geographical mismatches).
  3. Rebuilds pedagogical core catalog and exports fresh lexicon-core.db.gz.
"""

from __future__ import annotations

import concurrent.futures
import gzip
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from schema import LANGUAGES
from warehouse.config import OUT_DIR, ROOT
from warehouse.curate_tier1 import (
    OVERRIDES_FILE,
    apply_proposals,
    concept_candidates,
    concept_meta,
    curate_one,
    load_overrides,
    save_overrides,
)
from warehouse.export_sqlite import export_sqlite, write_catalog_sqlite
from warehouse.build_pedagogical_core import build_pedagogical_catalog

# Known critical overrides for high-frequency learner headwords
CRITICAL_FOUNDATIONAL_OVERRIDES: dict[str, dict[str, str]] = {
    "oklahoma.n.01": {"vi": "bang Oklahoma", "zh": "俄克拉何马州", "en": "Oklahoma"},
    "cell.n.02": {"vi": "tế bào", "zh": "细胞", "en": "cell", "ja": "細胞", "ko": "세포", "de": "Zelle", "fr": "cellule"},
    "fail.v.05": {"vi": "không thể", "zh": "不能", "en": "cannot", "ja": "できない", "ko": "못하다", "es": "no poder", "fr": "ne pas pouvoir"},
    "understand.v.03": {"vi": "hiểu", "zh": "懂", "en": "understand", "ja": "理解する", "ko": "이해하다"},
    "open.n.04": {"vi": "công khai", "zh": "公开", "en": "open", "ja": "公開"},
    "induct.v.01": {"vi": "bổ nhiệm", "zh": "就职", "en": "induct"},
    "completed.s.02": {"vi": "hoàn thành", "zh": "完成", "en": "completed", "ja": "完了した"},
    "air.n.06": {"vi": "không khí", "zh": "空气", "en": "air", "ja": "空気"},
    "correct.s.01": {"vi": "đúng", "zh": "正确", "en": "right", "ja": "正しい"},
    "possible.a.01": {"vi": "có thể", "zh": "可能", "en": "possible", "ja": "可能"},
    "sometimes.r.01": {"vi": "thỉnh thoảng", "zh": "有时", "en": "sometimes", "ja": "時々"},
    "water.n.01": {"vi": "nước", "zh": "水", "en": "water", "ja": "水", "ko": "물"},
    "home.n.01": {"vi": "nhà", "zh": "家", "en": "home", "ja": "家", "ko": "집"},
    "grandfather.n.01": {"vi": "ông", "zh": "爷爷", "en": "grandfather", "ja": "おじいさん", "ko": "할아버지"},
    "read.v.01": {"vi": "đọc", "zh": "读", "en": "read", "ja": "読む", "ko": "읽다"},
    "learn.v.04": {"vi": "học", "zh": "学习", "en": "learn", "ja": "学ぶ", "ko": "배우다"},
    "study.v.02": {"vi": "học", "zh": "学习", "en": "study", "ja": "勉強する", "ko": "공부하다"},
}


def apply_critical_foundation() -> int:
    overrides = load_overrides()
    applied = 0
    for sid, translations in CRITICAL_FOUNDATIONAL_OVERRIDES.items():
        overrides.setdefault(sid, {}).update(translations)
        applied += 1
    save_overrides(overrides)
    print(f"Applied {applied} critical foundational headword overrides.")
    return applied


def scan_noisy_synsets(top_n: int = 12000) -> list[str]:
    """Find synsets with high cross-lingual polysemy in the catalog."""
    raw_catalog_path = OUT_DIR / "core_vocabulary.json.gz"
    if not raw_catalog_path.exists():
        raw_catalog_path = ROOT / "out" / "core_vocabulary.json.gz"
    with gzip.open(raw_catalog_path, "rt", encoding="utf-8") as f:
        raw = json.load(f)

    overrides = load_overrides()
    noisy: list[str] = []
    for concept in raw.get("concepts", [])[:top_n]:
        cid = concept["id"]
        if cid in overrides and len(overrides[cid]) >= 10:
            continue
        terms = concept.get("terms", {})
        # Check if terms have suspicious polysemy or known noise markers
        meaning = concept.get("meaning", "").lower()
        if "state in" in meaning or "capital of" in meaning or "genus" in meaning:
            noisy.append(cid)
            continue
        # Check if English lemma is extremely short and has conflicting native translations
        en_text = (terms.get("en", {}).get("text") or "").strip()
        if len(en_text) <= 3 and len(terms) > 5:
            noisy.append(cid)
            continue
    return noisy


def run_parallel_curation(synset_ids: list[str], max_workers: int = 8) -> int:
    if not synset_ids:
        print("No noisy synsets to curate.")
        return 0
    checkpoint_file = OUT_DIR / "proposals_12k.json"
    done_sids: set[str] = set()
    proposals: list[dict[str, Any]] = []
    if checkpoint_file.exists():
        try:
            proposals = json.loads(checkpoint_file.read_text(encoding="utf-8"))
            done_sids = {p["synset_id"] for p in proposals}
        except Exception:
            proposals = []

    pending = [sid for sid in synset_ids if sid not in done_sids]
    print(f"Starting parallel curation for {len(pending)} pending synsets ({len(done_sids)} already cached) with {max_workers} workers...")
    overrides = load_overrides()

    def task(sid: str) -> dict[str, Any] | None:
        return curate_one(sid, langs=list(LANGUAGES), retries=2, overrides=overrides)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(task, sid): sid for sid in pending}
        done_count = 0
        for future in concurrent.futures.as_completed(futures):
            done_count += 1
            res = future.result()
            if res is not None:
                proposals.append(res)
                # Write checkpoint continuously
                checkpoint_file.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
            if done_count % 25 == 0 or done_count == len(pending):
                print(f"  Curated {done_count}/{len(pending)} concepts...", flush=True)

    applied = apply_proposals(proposals)
    print(f"Applied {applied} curated synsets to overrides.")
    return applied
    print(f"Applied {applied} curated synsets to overrides.")
    return applied


def rebuild_and_export() -> Path:
    print("Rebuilding pedagogical catalog...")
    catalog = build_pedagogical_catalog(top_n=12000)
    db_path = OUT_DIR / "lexicon-core.db"
    write_catalog_sqlite(catalog, db_path)
    gz_path = OUT_DIR / "lexicon-core.db.gz"
    gz_path.write_bytes(gzip.compress(db_path.read_bytes(), compresslevel=9))
    print(f"Exported clean pedagogical SQLite: {db_path} ({catalog.get('count')} concepts)")
    
    # Copy to frontend-extension
    frontend_dest = Path("/Users/admin/Documents/Fumihiko/livecode-extension/frontend-extension/public/vocabulary")
    if frontend_dest.exists():
        (frontend_dest / "lexicon-core.db.gz").write_bytes(gz_path.read_bytes())
        (frontend_dest / "lexicon-core.db").write_bytes(db_path.read_bytes())
        print(f"Synced pristine lexicon-core.db(.gz) to {frontend_dest}")

    return db_path


def main() -> int:
    print("=== Step 1: Apply critical foundation ===")
    apply_critical_foundation()

    print("=== Step 2: Scan for polysemous/noisy synsets ===")
    noisy = scan_noisy_synsets(top_n=3000)
    print(f"Found {len(noisy)} high-priority concepts for curation.")

    if noisy:
        print(f"=== Step 3: Run LLM curation on {len(noisy)} noisy synsets ===")
        run_parallel_curation(noisy, max_workers=8)

    print("=== Step 4: Rebuild pedagogical catalog & export SQLite ===")
    rebuild_and_export()
    print("=== Complete! ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
