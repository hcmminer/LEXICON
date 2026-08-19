from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from schema import LANGUAGES
from warehouse.db import connect, executemany
from warehouse.textutil import is_usable_lemma, normalize, script_ok

GOLD_SOURCES = frozenset({
    "wordnet",
    "omw-1.4",
    "wiktionary",
    "wiktextract",
    "wiktextract-multilingual",
    "wikidata",
})
GAP_CACHE_FILE = Path(__file__).resolve().parents[1] / "llm_gap_cache.json"

_LATIN_PRIMARY = frozenset({
    "es", "fr", "de", "pt", "id", "ms", "tr", "it", "nl", "pl",
    "cs", "sv", "da", "fi", "no", "hu", "ro", "sw", "en",
})


def gap_cache_key(synset_id: str, lang: str) -> str:
    return f"{synset_id}\t{lang}"


def load_gap_cache(path: Path = GAP_CACHE_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): str(v) for k, v in raw.items() if v}


def save_gap_cache(path: Path, cache: dict[str, str]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def missing_rank_slots(
    ranked: set[tuple[str, str]],
    catalog_ids: list[str],
    langs: tuple[str, ...],
) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for synset_id in catalog_ids:
        for lang in langs:
            if lang == "en":
                continue
            if (synset_id, lang) not in ranked:
                missing.append((synset_id, lang))
    return missing


def accept_llm_lemma(lang: str, text: str) -> str | None:
    lemma = text.strip()
    if not is_usable_lemma(lemma) or not script_ok(lang, lemma):
        return None
    if lang not in _LATIN_PRIMARY and lemma.isascii():
        return None
    return lemma


def backtranslate_ok(proposed_en: str, synset_en_lemmas: set[str]) -> bool:
    folded = {normalize(item) for item in synset_en_lemmas}
    return normalize(proposed_en) in folded


def may_write_llm(existing_source: str | None) -> bool:
    return existing_source is None or existing_source not in GOLD_SOURCES


GAP_SYSTEM_PROMPT = """You are a lexicographer. Given one WordNet synset, return the single most
natural learner headword in the requested language for THIS sense only.
Return JSON only: {"lemma": "<native lemma>", "back_en": "<English lemma of that sense>"}.
back_en must be one of the provided English lemmas."""


def propose_lemma(
    synset_id: str,
    pos: str,
    definition_en: str,
    en_lemmas: list[str],
    lang: str,
    candidates: list[str],
    call_json: Callable[..., Any] | None = None,
) -> str | None:
    from warehouse.llm import call_chat_json

    caller = call_json or call_chat_json
    user = "\n".join(
        [
            f"Synset: {synset_id}",
            f"POS: {pos}",
            f"Definition: {definition_en}",
            f"English lemmas: {', '.join(en_lemmas)}",
            f"Language: {lang}",
            f"Candidates: {', '.join(candidates) if candidates else '(none)'}",
        ]
    )
    for _ in range(2):
        try:
            payload = caller(GAP_SYSTEM_PROMPT, user)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        lemma = accept_llm_lemma(lang, str(payload.get("lemma") or ""))
        back_en = str(payload.get("back_en") or "")
        if lemma and backtranslate_ok(back_en, set(en_lemmas)):
            return lemma
    return None


BATCH_SYSTEM_PROMPT = """You are a lexicographer. Given one WordNet synset, return the single most
natural learner headword in EACH requested language for THIS sense only.
Return JSON only: {"<lang>": {"lemma": "<native lemma>", "back_en": "<English lemma>"}, ...}.
back_en must be one of the provided English lemmas."""


def propose_lemmas_for_synset(
    synset_id: str,
    pos: str,
    definition_en: str,
    en_lemmas: list[str],
    langs: list[str],
    call_json: Callable[..., Any] | None = None,
) -> dict[str, str]:
    from warehouse.llm import call_chat_json

    if not langs:
        return {}
    caller = call_json or call_chat_json
    user = "\n".join(
        [
            f"Synset: {synset_id}",
            f"POS: {pos}",
            f"Definition: {definition_en}",
            f"English lemmas: {', '.join(en_lemmas)}",
            f"Languages: {', '.join(langs)}",
        ]
    )
    accepted: dict[str, str] = {}
    pending = list(langs)
    for _ in range(2):
        if not pending:
            break
        try:
            payload = caller(BATCH_SYSTEM_PROMPT, user)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        still: list[str] = []
        for lang in pending:
            raw = payload.get(lang)
            if isinstance(raw, dict):
                lemma = accept_llm_lemma(lang, str(raw.get("lemma") or ""))
                back_en = str(raw.get("back_en") or "")
            else:
                lemma = accept_llm_lemma(lang, str(raw or ""))
                back_en = ""
            if lemma and (not back_en or backtranslate_ok(back_en, set(en_lemmas))):
                accepted[lang] = lemma
            else:
                still.append(lang)
        pending = still
    return accepted


def ingest_llm_gaps(limit: int | None = None, job: Any | None = None, top_n: int = 12000) -> None:
    cache = load_gap_cache()
    with connect() as conn:
        catalog_ids = [
            str(row["synset_id"])
            for row in conn.execute(
                """
                SELECT synset_id
                FROM core.concept_ranks
                WHERE lang = 'en' AND rank <= %s
                ORDER BY rank
                """,
                (top_n,),
            )
        ]
        ranked = {
            (str(row["synset_id"]), str(row["lang"]))
            for row in conn.execute("SELECT synset_id, lang FROM core.concept_ranks")
        }
        existing_source = {
            (str(row["synset_id"]), str(row["lang"])): str(row["source_id"])
            for row in conn.execute(
                """
                SELECT sl.synset_id, l.lang, sl.source_id
                FROM core.sense_lemmas sl
                JOIN core.lemmas l ON l.id = sl.lemma_id
                """
            )
        }
        meta = {
            str(row["id"]): (str(row["pos"]), str(row["definition_en"]))
            for row in conn.execute("SELECT id, pos, definition_en FROM core.synsets")
        }
        en_lemmas_by_synset: dict[str, list[str]] = {}
        for row in conn.execute(
            """
            SELECT sl.synset_id, l.text
            FROM core.sense_lemmas sl
            JOIN core.lemmas l ON l.id = sl.lemma_id
            WHERE l.lang = 'en'
            """
        ):
            en_lemmas_by_synset.setdefault(str(row["synset_id"]), []).append(str(row["text"]))

        slots = missing_rank_slots(ranked, catalog_ids, LANGUAGES)
        by_synset: dict[str, list[str]] = {}
        for synset_id, lang in slots:
            if not may_write_llm(existing_source.get((synset_id, lang))):
                continue
            by_synset.setdefault(synset_id, []).append(lang)
        synsets = list(by_synset)
        if limit is not None:
            synsets = synsets[:limit]
        total = len(synsets)
        pending_lemmas: list[tuple[str, str, str]] = []
        pending_links: list[tuple[str, str, str]] = []
        written = 0

        def flush() -> None:
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
                SELECT %s, l.id, 'llm'
                FROM core.lemmas l
                WHERE l.lang = %s AND l.normalized = %s
                ON CONFLICT DO NOTHING
                """,
                pending_links,
            )
            pending_lemmas.clear()
            pending_links.clear()
            conn.commit()

        for index, synset_id in enumerate(synsets, start=1):
            if job is not None:
                if job.cancelled():
                    job.log("cancelled")
                    break
                job.progress(index, total)
            langs = by_synset[synset_id]
            found: dict[str, str] = {}
            still: list[str] = []
            for lang in langs:
                key = gap_cache_key(synset_id, lang)
                cached = accept_llm_lemma(lang, cache.get(key, "")) if key in cache else None
                if cached:
                    found[lang] = cached
                else:
                    still.append(lang)
            if still:
                pos, definition = meta.get(synset_id, ("other", ""))
                proposed = propose_lemmas_for_synset(
                    synset_id,
                    pos,
                    definition,
                    en_lemmas_by_synset.get(synset_id, []),
                    still,
                )
                for lang, lemma in proposed.items():
                    cache[gap_cache_key(synset_id, lang)] = lemma
                    found[lang] = lemma
                if index % 20 == 0:
                    save_gap_cache(GAP_CACHE_FILE, cache)
            for lang, lemma in found.items():
                pending_lemmas.append((lang, lemma, normalize(lemma)))
                pending_links.append((synset_id, lang, normalize(lemma)))
                written += 1
            if len(pending_links) >= 200:
                flush()
        flush()
        save_gap_cache(GAP_CACHE_FILE, cache)
        conn.execute(
            """
            INSERT INTO core.ingest_runs (source_id, finished_at, row_count, notes)
            VALUES ('llm', now(), %s, %s)
            """,
            (written, f"slots={total}"),
        )
        conn.commit()
    if job is not None:
        job.log(f"wrote {written} llm lemmas")
    print(f"llm-gaps wrote {written} / {total}")
