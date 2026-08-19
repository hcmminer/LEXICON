from __future__ import annotations

import gzip
import json
from collections import defaultdict

from schema import WIKT_CODE_TO_ISO, WIKT_POS_TO_OURS
from warehouse.config import CACHE
from warehouse.db import connect, executemany
from warehouse.download_sources import ensure_data_source
from warehouse.ingest.kaikki_langs import KAIKKI_NATIVE_LANGS
from warehouse.textutil import is_usable_lemma, normalize, script_ok

__all__ = ["KAIKKI_NATIVE_LANGS", "ingest_wiktextract_native", "native_entry_links"]

OURS_TO_WN = {"noun": ("n",), "verb": ("v",), "adjective": ("a", "s"), "adverb": ("r",)}


def _english_words(entry: dict) -> list[str]:
    found: list[str] = []
    buckets = []
    if isinstance(entry.get("translations"), list):
        buckets.append(entry["translations"])
    for sense in entry.get("senses") or []:
        if not isinstance(sense, dict):
            continue
        if isinstance(sense.get("translations"), list):
            buckets.append(sense["translations"])
        for link in sense.get("links") or []:
            if not isinstance(link, (list, tuple)) or len(link) < 2:
                continue
            target = str(link[1]).strip()
            if not target or "#" in target:
                continue
            word = target.replace("_", " ").strip()
            if word and any(ch.isalpha() and ord(ch) < 0x300 for ch in word):
                found.append(word)
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
    pos_keys = (pos, *OURS_TO_WN.get(pos, ()))
    links: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for en in _english_words(entry):
        folded = normalize(en)
        if folded == normalize(lemma):
            continue
        for pos_key in pos_keys:
            for synset_id in en_index.get((folded, pos_key), [])[:3]:
                if synset_id not in seen:
                    seen.add(synset_id)
                    links.append((synset_id, lang, lemma))
    return links


def ingest_wiktextract_native(max_entries: int | None = None) -> None:
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
        pending_links: list[tuple[str, str, str]] = []

        def flush() -> None:
            nonlocal attached
            if not pending_lemmas:
                return
            executemany(
                conn,
                """
                INSERT INTO core.lemmas (lang, text, normalized)
                VALUES (%s, %s, %s)
                ON CONFLICT (lang, normalized) DO NOTHING
                """,
                pending_lemmas,
            )
            executemany(
                conn,
                """
                INSERT INTO core.sense_lemmas (synset_id, lemma_id, source_id)
                SELECT %s, l.id, 'wiktextract-multilingual'
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

        for lang, name in KAIKKI_NATIVE_LANGS.items():
            ensure_data_source(f"kaikki-{lang}")
            fname = f"kaikki.org-dictionary-{name.replace(' ', '_')}.jsonl.gz"
            path = CACHE / "kaikki-native" / fname
            if not path.exists():
                print(f"  kaikki-{lang} missing {path}")
                continue
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    scanned += 1
                    if max_entries is not None and scanned > max_entries:
                        break
                    if scanned % 200_000 == 0:
                        print(f"  wiktextract-native scanned {scanned:,} attached {attached:,}")
                        flush()
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for synset_id, link_lang, lemma in native_entry_links(entry, en_index):
                        pending_lemmas.append((link_lang, lemma, normalize(lemma)))
                        pending_links.append((synset_id, link_lang, normalize(lemma)))
                    if len(pending_links) >= 4000:
                        flush()
            if max_entries is not None and scanned > max_entries:
                break
        flush()
        conn.execute(
            """
            INSERT INTO core.ingest_runs (source_id, finished_at, row_count, notes)
            VALUES ('wiktextract-multilingual', now(), %s, %s)
            """,
            (attached, f"scanned={scanned}"),
        )
        conn.commit()
    print(f"wiktextract-native scanned {scanned} attached {attached}")
