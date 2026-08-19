from __future__ import annotations

import gzip
import json
import re
from collections.abc import Iterator
from pathlib import Path

from schema import WIKT_CODE_TO_ISO, WORDNET_POS_TO_OURS
from warehouse.config import CACHE
from warehouse.db import connect, executemany
from warehouse.download_sources import ensure_data_source
from warehouse.textutil import is_usable_lemma, normalize, script_ok

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


def iter_wikidata_entities(path: Path) -> Iterator[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip().rstrip(",")
            if stripped in {"", "[", "]"}:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def ingest_wikidata_lexemes(max_entities: int | None = None) -> None:
    ensure_data_source("wikidata-lexemes")
    path = CACHE / "latest-lexemes.json.gz"
    if not path.exists():
        raise SystemExit(f"missing {path}")

    with connect() as conn:
        offset_index: dict[tuple[int, str], str] = {}
        for row in conn.execute("SELECT wn_offset, pos, id FROM core.synsets"):
            pos = str(row["pos"])
            offset_index[(int(row["wn_offset"]), pos)] = str(row["id"])
            letter_pos = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}.get(pos)
            if letter_pos:
                offset_index[(int(row["wn_offset"]), letter_pos)] = str(row["id"])

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
                SELECT %s, l.id, 'wikidata'
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

        for entity in iter_wikidata_entities(path):
            scanned += 1
            if max_entities is not None and scanned > max_entities:
                break
            if scanned % 200_000 == 0:
                print(f"  wikidata scanned {scanned:,} attached {attached:,}")
                flush()
            for synset_id, lang, lemma in wikidata_lexeme_links(entity, offset_index):
                pending_lemmas.append((lang, lemma, normalize(lemma)))
                pending_links.append((synset_id, lang, normalize(lemma)))
            if len(pending_links) >= 4000:
                flush()
        flush()
        conn.execute(
            """
            INSERT INTO core.ingest_runs (source_id, finished_at, row_count, notes)
            VALUES ('wikidata', now(), %s, %s)
            """,
            (attached, f"scanned={scanned}"),
        )
        conn.commit()
    print(f"wikidata scanned {scanned} attached {attached}")
