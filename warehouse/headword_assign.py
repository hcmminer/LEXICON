from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from schema import LANGUAGES
from warehouse.db import connect, executemany
from warehouse.textutil import is_function_word, is_usable_lemma, normalize, script_ok

TOKEN_SPLIT = re.compile(r"[\s,;/+]+")


def drop_bound_fragments(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    texts = [str(item.get("text") or "").strip() for item in options]
    kept: list[dict[str, Any]] = []
    for item, text in zip(options, texts):
        parts = text.split()
        if len(parts) == 1 and any(text != other and text in other.split() for other in texts):
            continue
        kept.append(item)
    return kept or options


def is_learner_headword(lang: str, text: str) -> bool:
    stripped = (text or "").strip()
    if not is_usable_lemma(stripped):
        return False
    if lang and not script_ok(lang, stripped):
        return False
    if is_function_word(lang, stripped):
        return False
    tokens = [tok for tok in TOKEN_SPLIT.split(stripped) if tok]
    if len(tokens) >= 2:
        func_n = sum(1 for tok in tokens if is_function_word(lang, tok))
        if func_n >= max(1, len(tokens) - 1):
            return False
    return True


def assign_unique_headwords(
    synset_ids: list[str],
    langs: tuple[str, ...],
    candidates: dict[tuple[str, str], list[dict[str, Any]]],
    max_uses: int = 2,
    max_uses_by_lang: dict[str, int] | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    used: dict[str, dict[str, int]] = defaultdict(dict)
    assigned: dict[tuple[str, str], dict[str, Any]] = {}
    limits = max_uses_by_lang or {}
    for synset_id in synset_ids:
        for lang in langs:
            options = candidates.get((synset_id, lang), [])
            picked: dict[str, Any] | None = None
            limit = limits.get(lang, max_uses)
            for option in options:
                text = str(option.get("text") or "").strip()
                if not is_learner_headword(lang, text):
                    continue
                key = normalize(text)
                if used[lang].get(key, 0) >= limit:
                    continue
                picked = option
                used[lang][key] = used[lang].get(key, 0) + 1
                break
            if picked is not None:
                assigned[(synset_id, lang)] = picked
    return assigned


def _candidate_score(lang: str, text: str, zipf: float | None, span: int) -> float:
    score = float(zipf or 0.0) - (span * 0.02)
    stripped = text.strip()
    if lang == "vi" and " " in stripped:
        score += 0.6
    if lang in {"zh", "ja", "ko"} and len(stripped) >= 2:
        score += 0.5
    if lang in {"zh", "ja"} and len(stripped) == 1:
        score -= 0.8
    return score


def apply_bound_lemma_fixes() -> int:
    """Replace bound-syllable headwords with a compound sibling. Never drop ranks."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT cr.synset_id, cr.lang, cr.lemma_id AS current_id,
                   cur.text AS current_text, l.id AS lemma_id, l.text, l.zipf
            FROM core.concept_ranks cr
            JOIN core.lemmas cur ON cur.id = cr.lemma_id
            JOIN core.sense_lemmas sl ON sl.synset_id = cr.synset_id
            JOIN core.lemmas l ON l.id = sl.lemma_id AND l.lang = cr.lang
            WHERE POSITION(' ' IN cur.text) = 0
            """
        ).fetchall()
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        current: dict[tuple[str, str], int] = {}
        seen: set[tuple[str, str, int]] = set()
        for row in rows:
            key = (str(row["synset_id"]), str(row["lang"]))
            current[key] = int(row["current_id"])
            lemma_id = int(row["lemma_id"])
            dedupe = (key[0], key[1], lemma_id)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            text = str(row["text"] or "")
            grouped[key].append(
                {
                    "lemma_id": lemma_id,
                    "text": text,
                    "score": _candidate_score(key[1], text, row["zipf"], 1),
                }
            )
        updates: list[tuple[int, str, str]] = []
        for key, options in grouped.items():
            options.sort(key=lambda item: item["score"], reverse=True)
            options = drop_bound_fragments(options)
            if not options:
                continue
            best = options[0]
            if int(best["lemma_id"]) != current[key] and is_learner_headword(key[1], str(best["text"])):
                updates.append((int(best["lemma_id"]), key[0], key[1]))
        if updates:
            executemany(
                conn,
                """
                UPDATE core.concept_ranks
                SET lemma_id = %s
                WHERE synset_id = %s AND lang = %s
                """,
                updates,
            )
            conn.commit()
        print(f"bound-lemma fixes={len(updates)}")
        return len(updates)


def apply_unique_headwords(top_n: int = 12000, max_uses: int = 2) -> None:
    with connect() as conn:
        synset_ids = [
            str(row["synset_id"])
            for row in conn.execute(
                """
                SELECT synset_id FROM core.concept_ranks
                WHERE lang = 'en'
                ORDER BY rank
                LIMIT %s
                """,
                (top_n,),
            )
        ]
        if not synset_ids:
            return
        conn.execute("CREATE TEMP TABLE _unique_synsets (synset_id TEXT PRIMARY KEY)")
        executemany(conn, "INSERT INTO _unique_synsets(synset_id) VALUES (%s)", [(sid,) for sid in synset_ids])
        rows = conn.execute(
            """
            SELECT sl.synset_id, l.lang, l.id AS lemma_id, l.text, l.zipf,
                   (
                       SELECT COUNT(DISTINCT x.synset_id)
                       FROM core.sense_lemmas x
                       WHERE x.lemma_id = l.id
                   ) AS span
            FROM core.sense_lemmas sl
            JOIN core.lemmas l ON l.id = sl.lemma_id
            JOIN _unique_synsets u ON u.synset_id = sl.synset_id
            """
        ).fetchall()
        candidates: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        seen: set[tuple[str, str, int]] = set()
        for row in rows:
            key = (str(row["synset_id"]), str(row["lang"]))
            lemma_id = int(row["lemma_id"])
            dedupe = (key[0], key[1], lemma_id)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            text = str(row["text"] or "")
            candidates[key].append(
                {
                    "lemma_id": lemma_id,
                    "text": text,
                    "score": _candidate_score(key[1], text, row["zipf"], int(row["span"] or 0)),
                }
            )
        for key, options in list(candidates.items()):
            options.sort(key=lambda item: item["score"], reverse=True)
            candidates[key] = drop_bound_fragments(options)
        assigned = assign_unique_headwords(
            synset_ids,
            LANGUAGES,
            candidates,
            max_uses=max_uses,
            max_uses_by_lang={"en": 8},
        )
        conn.execute("TRUNCATE core.concept_ranks")
        by_lang: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for (synset_id, lang), item in assigned.items():
            by_lang[lang].append((synset_id, int(item["lemma_id"])))
        insert_rows: list[tuple[str, str, int, int]] = []
        for lang, pairs in by_lang.items():
            for index, (synset_id, lemma_id) in enumerate(pairs, start=1):
                insert_rows.append((synset_id, lang, index, lemma_id))
        executemany(
            conn,
            """
            INSERT INTO core.concept_ranks (synset_id, lang, rank, lemma_id)
            VALUES (%s, %s, %s, %s)
            """,
            insert_rows,
        )
        conn.execute(
            """
            CREATE TEMP TABLE _new_ranks AS
            SELECT cr.synset_id, cr.lang,
                   ROW_NUMBER() OVER (
                       PARTITION BY cr.lang
                       ORDER BY l.zipf DESC NULLS LAST, cr.synset_id
                   ) AS rank,
                   cr.lemma_id
            FROM core.concept_ranks cr
            JOIN core.lemmas l ON l.id = cr.lemma_id
            """
        )
        conn.execute("TRUNCATE core.concept_ranks")
        conn.execute(
            """
            INSERT INTO core.concept_ranks (synset_id, lang, rank, lemma_id)
            SELECT synset_id, lang, rank, lemma_id FROM _new_ranks
            """
        )
        conn.commit()
        print(f"unique-headwords assigned={len(assigned)} synsets={len(synset_ids)}")
