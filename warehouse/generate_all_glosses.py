#!/usr/bin/env python3
"""
warehouse/generate_all_glosses.py

Native localized glosses for every term, incremental + context-aware:

  * Resume from warehouse/glosses_cache.json — top 6000/9000/12000 only
    translates concepts not already complete from a previous run.
  * English is copied from the WordNet definition (no LLM call).
  * Each request only asks for *missing* langs of *incomplete* concepts.
  * Batches are packed by output-slot budget (langs × concepts), not a
    tiny fixed concept count — sized for a large-context / large-output model.
  * Concurrent workers + retry/backoff via warehouse.llm.call_chat_json.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Callable

from warehouse.config import OUT_DIR
from warehouse.gloss_generator import (
    GLOSS_CACHE_FILE,
    generate_missing_glosses_batch,
    load_gloss_cache,
    save_gloss_cache,
)
from warehouse.llm import llm_config

# Pack by output slots (one slot = one lang gloss). Gemini-class models
# handle tens of thousands of output tokens; 1200 slots ≈ 70 concepts × 17 langs
# ≈ 20k output tokens — well under a 65k cap, 7× fewer calls than batch=10.
SLOT_BUDGET = 1200
DEFAULT_WORKERS = 3
BATCH_TIMEOUT = 180.0


def load_union(top_n: int) -> dict:
    path = OUT_DIR / "core_vocabulary.json.gz"
    if not path.exists():
        path = Path(__file__).resolve().parents[1] / "out" / "core_vocabulary.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        catalog = json.load(f)
    catalog["concepts"] = catalog["concepts"][:top_n]
    print(f"loaded {len(catalog['concepts'])} concepts (top {top_n})", flush=True)
    return catalog


def wanted_langs(concept: dict, langs: list[str] | None) -> list[str]:
    return [lang for lang in (concept.get("terms") or {}) if langs is None or lang in langs]


def fill_english_glosses(concepts: list[dict], cache: dict) -> int:
    """Copy the English definition into the cache. Never spend an LLM call on `en`."""
    filled = 0
    for concept in concepts:
        if "en" not in (concept.get("terms") or {}):
            continue
        meaning = (concept.get("meaning") or "").strip()
        if not meaning:
            continue
        slot = cache.setdefault(concept["id"], {})
        if not slot.get("en"):
            slot["en"] = meaning
            filled += 1
    return filled


def missing_langs(concept: dict, langs: list[str] | None, cache: dict) -> list[str]:
    have = cache.get(concept["id"], {})
    return [lang for lang in wanted_langs(concept, langs) if lang != "en" and not have.get(lang)]


def collect_pending(catalog: dict, langs: list[str] | None, cache: dict) -> list[tuple[dict, list[str]]]:
    pending: list[tuple[dict, list[str]]] = []
    for concept in catalog["concepts"]:
        miss = missing_langs(concept, langs, cache)
        if miss:
            pending.append((concept, miss))
    return pending


def pack_by_slots(
    pending: list[tuple[dict, list[str]]],
    slot_budget: int = SLOT_BUDGET,
) -> list[list[tuple[dict, list[str]]]]:
    batches: list[list[tuple[dict, list[str]]]] = []
    current: list[tuple[dict, list[str]]] = []
    slots = 0
    for item in pending:
        n = max(1, len(item[1]))
        if current and slots + n > slot_budget:
            batches.append(current)
            current, slots = [], 0
        current.append(item)
        slots += n
    if current:
        batches.append(current)
    return batches


def _slim_concepts(batch: list[tuple[dict, list[str]]]) -> list[dict]:
    slim: list[dict] = []
    for concept, miss in batch:
        terms = concept.get("terms") or {}
        slim.append({
            "id": concept["id"],
            "pos": concept.get("pos", ""),
            "meaning": concept.get("meaning", ""),
            "terms": {lang: terms[lang] for lang in miss if lang in terms},
        })
    return slim


def run(
    top_n: int,
    limit: int | None,
    langs: list[str] | None,
    workers: int = DEFAULT_WORKERS,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    slot_budget: int = SLOT_BUDGET,
) -> int:
    def _log(line: str) -> None:
        print(line, flush=True)
        if log:
            log(line)

    if llm_config() is None:
        _log("ERROR: LLM not configured (LEXICON_LLM_BASE_URL/API_KEY/MODEL).")
        return 1

    catalog = load_union(top_n)
    cache = load_gloss_cache()
    en_filled = fill_english_glosses(catalog["concepts"], cache)
    pending = collect_pending(catalog, langs, cache)
    skipped = len(catalog["concepts"]) - len(pending)
    total = len(pending)
    batches = pack_by_slots(pending, slot_budget=slot_budget)
    _log(
        f"reuse {skipped} complete, {en_filled} en-copied, "
        f"{total} pending → {len(batches)} requests "
        f"(slot budget {slot_budget}, workers {workers})"
    )
    if progress:
        progress(0, total)
    if not pending:
        save_gloss_cache(cache)
        _log(f"nothing to do; cache has {len(cache)} concepts")
        return 0

    done = 0

    def worker_batch(batch: list[tuple[dict, list[str]]]) -> tuple[list[tuple[dict, list[str]]], dict, str | None]:
        try:
            return batch, generate_missing_glosses_batch(_slim_concepts(batch), timeout=BATCH_TIMEOUT), None
        except Exception as exc:  # noqa: BLE001
            return batch, {}, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker_batch, batch) for batch in batches]
        for fut in concurrent.futures.as_completed(futures):
            if cancelled and cancelled():
                for pending_fut in futures:
                    pending_fut.cancel()
                _log("cancelled")
                break
            batch, glossed, error = fut.result()
            if error:
                _log(f"batch failed ({len(batch)} concepts): {error[:200]}")
            for concept, _miss in batch:
                cid = concept["id"]
                slot = cache.setdefault(cid, {})
                for lang, gloss in glossed.get(cid, {}).items():
                    slot[lang] = gloss
            done += len(batch)
            tmp = GLOSS_CACHE_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(GLOSS_CACHE_FILE)
            if progress:
                progress(done, total)
            _log(f"progress {done}/{total} concepts glossed")
            if limit is not None and done >= limit:
                break

    save_gloss_cache(cache)
    _log(f"done: {done} concepts attempted; cache has {len(cache)} concepts")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate native localized glosses for all terms")
    parser.add_argument("--top", type=int, default=3000, choices=(3000, 6000, 9000, 12000))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--langs", type=str, default=None)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--slot-budget", type=int, default=SLOT_BUDGET)
    args = parser.parse_args()
    langs = [lang.strip() for lang in args.langs.split(",") if lang.strip()] if args.langs else None
    return run(args.top, args.limit, langs, workers=args.workers, slot_budget=args.slot_budget)


if __name__ == "__main__":
    raise SystemExit(main())
