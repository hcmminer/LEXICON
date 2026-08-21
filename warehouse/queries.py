from __future__ import annotations

from typing import Any

from schema import LANGUAGES
from warehouse.db import connect
from warehouse.gloss_generator import load_gloss_cache


def warehouse_stats() -> dict[str, Any]:
    with connect() as conn:
        counts = {
            row["t"]: row["n"]
            for row in conn.execute(
                """
                SELECT 'synsets' AS t, COUNT(*)::int AS n FROM core.synsets
                UNION ALL SELECT 'lemmas', COUNT(*)::int FROM core.lemmas
                UNION ALL SELECT 'sense_lemmas', COUNT(*)::int FROM core.sense_lemmas
                UNION ALL SELECT 'ranks', COUNT(*)::int FROM core.concept_ranks
                UNION ALL SELECT 'readings', COUNT(*)::int FROM core.readings
                """
            )
        }
        coverage = conn.execute(
            """
            SELECT lang, COUNT(*)::int AS filled, MAX(rank)::int AS max_rank
            FROM core.concept_ranks
            GROUP BY lang
            ORDER BY lang
            """
        ).fetchall()
        runs = conn.execute(
            """
            SELECT source_id, started_at, finished_at, row_count, notes
            FROM core.ingest_runs
            ORDER BY id DESC
            LIMIT 12
            """
        ).fetchall()
    by_lang = {row["lang"]: row for row in coverage}
    return {
        "counts": counts,
        "coverage": [
            {
                "lang": lang,
                "filled": by_lang.get(lang, {}).get("filled", 0),
                "max_rank": by_lang.get(lang, {}).get("max_rank", 0),
            }
            for lang in LANGUAGES
        ],
        "runs": runs,
        "catalog_size": by_lang.get("en", {}).get("filled", 0),
    }


def search_catalog(
    lang: str,
    q: str,
    max_rank: int,
    limit: int = 40,
    offset: int = 0,
    distinct: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    query = f"%{q.strip()}%" if q.strip() else None
    gloss_cache = load_gloss_cache()
    with connect() as conn:
        if distinct:
            total = conn.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM (
                    SELECT cr.synset_id, l.text,
                           ROW_NUMBER() OVER (PARTITION BY l.text ORDER BY cr.rank, cr.synset_id) as rn
                    FROM core.concept_ranks cr
                    JOIN core.lemmas l ON l.id = cr.lemma_id
                    JOIN core.synsets s ON s.id = cr.synset_id
                    WHERE cr.lang = %s AND cr.rank <= %s
                      AND (%s::text IS NULL OR l.text ILIKE %s OR s.id ILIKE %s OR s.definition_en ILIKE %s)
                ) sub
                WHERE rn = 1
                """,
                (lang, max_rank, query, query, query, query),
            ).fetchone()["n"]
            rows = conn.execute(
                """
                SELECT s.id, s.pos, s.definition_en, l.text, cr.rank
                FROM (
                    SELECT cr.synset_id, cr.lemma_id, cr.rank,
                           ROW_NUMBER() OVER (PARTITION BY l.text ORDER BY cr.rank, cr.synset_id) as rn
                    FROM core.concept_ranks cr
                    JOIN core.lemmas l ON l.id = cr.lemma_id
                    JOIN core.synsets s ON s.id = cr.synset_id
                    WHERE cr.lang = %s AND cr.rank <= %s
                      AND (%s::text IS NULL OR l.text ILIKE %s OR s.id ILIKE %s OR s.definition_en ILIKE %s)
                ) sub
                JOIN core.concept_ranks cr ON cr.synset_id = sub.synset_id AND cr.lemma_id = sub.lemma_id AND cr.lang = %s
                JOIN core.lemmas l ON l.id = cr.lemma_id
                JOIN core.synsets s ON s.id = cr.synset_id
                WHERE sub.rn = 1
                ORDER BY cr.rank
                LIMIT %s OFFSET %s
                """,
                (lang, max_rank, query, query, query, query, lang, limit, offset),
            ).fetchall()
        else:
            total = conn.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM core.concept_ranks cr
                JOIN core.lemmas l ON l.id = cr.lemma_id
                JOIN core.synsets s ON s.id = cr.synset_id
                WHERE cr.lang = %s AND cr.rank <= %s
                  AND (%s::text IS NULL OR l.text ILIKE %s OR s.id ILIKE %s OR s.definition_en ILIKE %s)
                """,
                (lang, max_rank, query, query, query, query),
            ).fetchone()["n"]
            rows = conn.execute(
                """
                SELECT s.id, s.pos, s.definition_en, l.text, cr.rank
                FROM core.concept_ranks cr
                JOIN core.lemmas l ON l.id = cr.lemma_id
                JOIN core.synsets s ON s.id = cr.synset_id
                WHERE cr.lang = %s AND cr.rank <= %s
                  AND (%s::text IS NULL OR l.text ILIKE %s OR s.id ILIKE %s OR s.definition_en ILIKE %s)
                ORDER BY cr.rank
                LIMIT %s OFFSET %s
                """,
                (lang, max_rank, query, query, query, query, limit, offset),
            ).fetchall()

    result_rows: list[dict[str, Any]] = []
    for r in rows:
        row_dict = dict(r)
        cid = row_dict["id"]
        row_dict["native_gloss"] = gloss_cache.get(cid, {}).get(lang)
        result_rows.append(row_dict)

    return result_rows, total


def get_concept(synset_id: str) -> dict[str, Any] | None:
    gloss_cache = load_gloss_cache()
    with connect() as conn:
        synset = conn.execute(
            "SELECT id, pos, definition_en FROM core.synsets WHERE id = %s",
            (synset_id,),
        ).fetchone()
        if synset is None:
            return None
        terms = conn.execute(
            """
            SELECT cr.lang, cr.rank, l.text,
                (
                    SELECT jsonb_object_agg(r.system, r.value)
                    FROM core.readings r
                    WHERE r.lemma_id = l.id
                ) AS readings
            FROM core.concept_ranks cr
            JOIN core.lemmas l ON l.id = cr.lemma_id
            WHERE cr.synset_id = %s
            ORDER BY cr.lang
            """,
            (synset_id,),
        ).fetchall()

    terms_map = {}
    for row in terms:
        d = dict(row)
        d["native_gloss"] = gloss_cache.get(synset_id, {}).get(d["lang"])
        terms_map[d["lang"]] = d

    return {"synset": synset, "terms": terms_map}
