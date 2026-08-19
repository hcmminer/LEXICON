#!/usr/bin/env python3
"""
warehouse/curate_tier1.py

Offline Curation Tool for Tier 1 Core Vocabulary.

Two workflows:
  1. Heuristic / manual curation via `curated_overrides.json` (checked in).
  2. LLM-assisted curation: scan ambiguous concepts, ask an LLM to pick the
     best natural translation per language, review, then apply to overrides.

CLI:
  python -m warehouse.curate_tier1 scan [--lang vi] [--limit 20]
  python -m warehouse.curate_tier1 curate [--limit 5] [--langs vi,zh,en]
  python -m warehouse.curate_tier1 apply --file proposals.json
  python -m warehouse.curate_tier1 audit
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from warehouse.db import connect
from warehouse.llm import pick_best_translations, sanitize_candidate
from schema import LANGUAGES

OVERRIDES_FILE = Path(__file__).parent / "curated_overrides.json"


def load_overrides() -> dict[str, dict[str, str]]:
    if OVERRIDES_FILE.exists():
        return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    return {}


def save_overrides(overrides: dict[str, dict[str, str]]) -> None:
    payload = json.dumps(overrides, ensure_ascii=False, indent=2) + "\n"
    OVERRIDES_FILE.write_text(payload, encoding="utf-8")


def add_curated_concept(synset_id: str, translations: dict[str, str]) -> None:
    overrides = load_overrides()
    overrides.setdefault(synset_id, {}).update(translations)
    save_overrides(overrides)


def ambiguous_synsets(lang: str = "vi", limit: int = 20) -> list[dict[str, Any]]:
    """Synsets (ranked, not yet curated) whose chosen headword in `lang` maps
    to 2+ synsets across the whole WordNet graph — the noisy ones."""
    with connect() as conn:
        rows = conn.execute(
            """
            WITH lemma_counts AS (
                SELECT lemma_id, COUNT(DISTINCT synset_id)::int AS count
                FROM core.sense_lemmas
                GROUP BY lemma_id
            )
            SELECT DISTINCT ON (cr.synset_id)
                s.id AS synset_id,
                s.pos,
                s.definition_en,
                l.text AS current_text,
                lc.count AS synset_count,
                cr.rank
            FROM core.concept_ranks cr
            JOIN core.synsets s ON s.id = cr.synset_id
            JOIN core.lemmas l ON l.id = cr.lemma_id
            JOIN lemma_counts lc ON lc.lemma_id = l.id
            WHERE cr.lang = %s AND lc.count >= 2
            ORDER BY cr.synset_id, cr.rank
            LIMIT %s
            """,
            (lang, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def ambiguous_synsets_all(min_count: int = 8, limit: int = 150) -> list[dict[str, Any]]:
    """Highest-priority un-curated synsets (by EN rank) that have ANY lemma
    (in any language) mapping to `min_count`+ synsets across WordNet."""
    overrides = load_overrides()
    with connect() as conn:
        rows = conn.execute(
            """
            WITH lemma_counts AS (
                SELECT lemma_id, COUNT(DISTINCT synset_id)::int AS count
                FROM core.sense_lemmas
                GROUP BY lemma_id
            )
            SELECT DISTINCT
                s.id AS synset_id,
                s.pos,
                s.definition_en,
                cr.rank
            FROM core.concept_ranks cr
            JOIN core.synsets s ON s.id = cr.synset_id
            JOIN core.sense_lemmas sl ON sl.synset_id = s.id
            JOIN lemma_counts lc ON lc.lemma_id = sl.lemma_id
            WHERE cr.lang = 'en' AND cr.rank <= 3000 AND lc.count >= %s
            ORDER BY cr.rank
            LIMIT %s
            """,
            (min_count, limit * 3),
        ).fetchall()
    result = [dict(r) for r in rows if r["synset_id"] not in overrides][:limit]
    return result


def concept_candidates(synset_id: str, langs: list[str]) -> dict[str, list[str]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT l.lang, l.text
            FROM core.sense_lemmas sl
            JOIN core.lemmas l ON l.id = sl.lemma_id
            LEFT JOIN core.function_words fw
                ON fw.lang = l.lang AND fw.normalized = l.normalized
            WHERE sl.synset_id = %s AND fw.normalized IS NULL
            ORDER BY l.lang, l.zipf DESC NULLS LAST
            """,
            (synset_id,),
        ).fetchall()
    out: dict[str, list[str]] = {lang: [] for lang in langs}
    for row in rows:
        if row["lang"] in out and row["text"] not in out[row["lang"]]:
            out[row["lang"]].append(row["text"])
    return out


def concept_meta(synset_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, pos, definition_en FROM core.synsets WHERE id = %s",
            (synset_id,),
        ).fetchone()
    return dict(row) if row else None


def run_curation_batch(
    synset_ids: list[str],
    langs: list[str] | None = None,
    retries: int = 2,
) -> list[dict[str, Any]]:
    overrides = load_overrides()
    proposals: list[dict[str, Any]] = []
    for synset_id in synset_ids:
        proposal = curate_one(synset_id, langs, retries, overrides)
        if proposal is not None:
            proposals.append(proposal)
    return proposals


def curate_one(
    synset_id: str,
    langs: list[str] | None,
    retries: int = 2,
    overrides: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Curation for a single synset across (all) languages. Returns a proposal
    dict, or None when the synset is missing or the LLM fails every attempt."""
    overrides = overrides or load_overrides()
    meta = concept_meta(synset_id)
    if meta is None:
        return None
    all_candidates = concept_candidates(synset_id, list(LANGUAGES))
    langs_to_ask = langs or [lang for lang in LANGUAGES if all_candidates.get(lang)]
    candidates = {lang: all_candidates[lang] for lang in langs_to_ask}
    for lang in langs_to_ask:
        if lang in overrides.get(synset_id, {}):
            candidates[lang] = [overrides[synset_id][lang]]
    chosen: dict[str, str] = {}
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            chosen = pick_best_translations(synset_id, meta["pos"], meta["definition_en"], candidates)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if not chosen and last_error is not None:
        print(f"  SKIP {synset_id}: {last_error}")
        return None
    current = concept_candidates(synset_id, langs_to_ask)
    return {
        "synset_id": synset_id,
        "pos": meta["pos"],
        "meaning": meta["definition_en"],
        "candidates": {k: v for k, v in candidates.items()},
        "current": {k: (v[0] if v else None) for k, v in current.items()},
        "proposed": chosen,
    }


def curate_with_checkpoint(
    synset_ids: list[str],
    out_path: Path,
    langs: list[str] | None = None,
) -> int:
    """Curate a batch, writing a proposal file after EVERY concept so progress
    survives interruption. Skips synsets already present in the file."""
    proposals: list[dict[str, Any]] = []
    done = set()
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            proposals = existing
            done = {p["synset_id"] for p in existing}
        except Exception:
            proposals = []
    overrides = load_overrides()
    pending = [sid for sid in synset_ids if sid not in done]
    for index, synset_id in enumerate(pending, start=1):
        proposal = curate_one(synset_id, langs, overrides=overrides)
        if proposal is not None:
            proposals.append(proposal)
            overrides = load_overrides()  # re-read so manual edits stay visible
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(json.dumps(proposals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(out_path)
        if index % 10 == 0 or index == len(pending):
            print(f"  progress {index}/{len(pending)} (total proposals {len(proposals)})", flush=True)
    return len(proposals)


def apply_proposals(proposals: list[dict[str, Any]]) -> int:
    overrides = load_overrides()
    applied = 0
    for proposal in proposals:
        synset_id = proposal.get("synset_id")
        proposed = proposal.get("proposed") or {}
        if not synset_id or not proposed:
            continue
        overrides.setdefault(synset_id, {}).update(proposed)
        applied += 1
    save_overrides(overrides)
    return applied


def audit() -> dict[str, Any]:
    overrides = load_overrides()
    return {"total_overrides": len(overrides)}


def _print_table(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        print(
            f"{row['synset_id']:<24} {row.get('rank', '?'):>5}  "
            f"{row.get('current_text', ''):<14} [{row.get('synset_count', '?')}x]  "
            f"{(row.get('definition_en') or '')[:60]}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Tier 1 curation tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="list ambiguous un-curated synsets")
    scan.add_argument("--lang", default="vi")
    scan.add_argument("--limit", type=int, default=20)

    cur = sub.add_parser("curate", help="LLM-propose translations (dry run, no write)")
    cur.add_argument("--limit", type=int, default=5)
    cur.add_argument("--langs", default="vi,zh,en")
    cur.add_argument("--out", type=Path, default=Path("proposals.json"))

    ap = sub.add_parser("apply", help="write proposals into curated_overrides.json")
    ap.add_argument("--file", type=Path, required=True)

    sub.add_parser("audit", help="show override count")

    args = parser.parse_args()

    if args.cmd == "scan":
        rows = ambiguous_synsets(args.lang, args.limit)
        _print_table(rows)
        return 0
    if args.cmd == "curate":
        langs = [lang.strip() for lang in args.langs.split(",") if lang.strip()] or None
        scan_rows = ambiguous_synsets_all(limit=args.limit)
        synset_ids = [row["synset_id"] for row in scan_rows]
        count = curate_with_checkpoint(synset_ids, args.out, langs)
        print(f"checkpoint file {args.out} has {count} proposals")
        return 0
    if args.cmd == "apply":
        proposals = json.loads(args.file.read_text(encoding="utf-8"))
        count = apply_proposals(proposals)
        print(f"applied {count} concepts")
        return 0
    if args.cmd == "audit":
        print(audit())
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
