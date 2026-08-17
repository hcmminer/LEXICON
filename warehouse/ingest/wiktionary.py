from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path

from schema import WIKT_CODE_TO_ISO, WIKT_POS_TO_OURS
from warehouse.config import CACHE
from warehouse.db import connect, executemany
from warehouse.textutil import is_usable_lemma, normalize, script_ok

KAIKKI = CACHE / "kaikki.org-dictionary-English.jsonl.gz"
OURS_TO_WN = {"noun": ("n",), "verb": ("v",), "adjective": ("a", "s"), "adverb": ("r",)}


def _translations(entry: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
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
            iso = WIKT_CODE_TO_ISO.get(str(item.get("code") or item.get("lang_code") or ""))
            word = item.get("word")
            if iso is None or iso == "en" or not isinstance(word, str):
                continue
            word = word.strip()
            if not is_usable_lemma(word) or not script_ok(iso, word):
                continue
            if word not in found[iso]:
                found[iso].append(word)
    return found


def ingest_wiktionary(max_entries: int | None = None) -> None:
    if not KAIKKI.exists():
        raise SystemExit(f"missing {KAIKKI}")

    with connect() as conn:
        en_index: dict[tuple[str, str], list[str]] = defaultdict(list)
        for row in conn.execute(
            """
            SELECT l.normalized, s.pos, s.id
            FROM core.sense_lemmas sl
            JOIN core.lemmas l ON l.id = sl.lemma_id
            JOIN core.synsets s ON s.id = sl.synset_id
            WHERE l.lang = 'en'
            """
        ):
            en_index[(row["normalized"], row["pos"])].append(row["id"])

        scanned = 0
        attached = 0
        pending_lemmas: list[tuple[str, str, str]] = []
        pending_links: list[tuple[str, str, str, str]] = []

        def flush() -> None:
            nonlocal attached
            if not pending_lemmas:
                return
            executemany(conn,
                """
                INSERT INTO core.lemmas (lang, text, normalized)
                VALUES (%s, %s, %s)
                ON CONFLICT (lang, normalized) DO NOTHING
                """,
                pending_lemmas,
            )
            executemany(conn,
                """
                INSERT INTO core.sense_lemmas (synset_id, lemma_id, source_id)
                SELECT %s, l.id, 'wiktextract'
                FROM core.lemmas l
                WHERE l.lang = %s AND l.normalized = %s
                ON CONFLICT DO NOTHING
                """,
                pending_links,
            )
            attached += len(pending_links)
            pending_lemmas.clear()
            pending_links.clear()
            conn.commit()

        opened = gzip.open(KAIKKI, "rt", encoding="utf-8")
        with opened as handle:
            for line in handle:
                scanned += 1
                if max_entries is not None and scanned > max_entries:
                    break
                if scanned % 200_000 == 0:
                    print(f"  wiktionary scanned {scanned:,} attached {attached:,}")
                    flush()
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                en = str(entry.get("word") or "").strip()
                pos = WIKT_POS_TO_OURS.get(str(entry.get("pos") or ""))
                if not en or pos is None:
                    continue
                synset_ids: list[str] = []
                for wn_pos in OURS_TO_WN.get(pos, ()):
                    synset_ids.extend(en_index.get((normalize(en), wn_pos), []))
                if not synset_ids:
                    continue
                translations = _translations(entry)
                if not translations:
                    continue
                for lang, lemmas in translations.items():
                    for lemma in lemmas:
                        pending_lemmas.append((lang, lemma, normalize(lemma)))
                        for synset_id in synset_ids[:3]:
                            pending_links.append((synset_id, lang, normalize(lemma)))
                if len(pending_links) >= 4000:
                    flush()
        flush()
        conn.execute(
            """
            INSERT INTO core.ingest_runs (source_id, finished_at, row_count, notes)
            VALUES ('wiktextract', now(), %s, %s)
            """,
            (attached, f"scanned={scanned}"),
        )
        conn.commit()
    print(f"wiktionary scanned {scanned} attached {attached}")
