from __future__ import annotations

from typing import Any

from schema import LANGUAGES
from warehouse.db import connect


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


def search_catalog(lang: str, q: str, max_rank: int, limit: int = 40, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    query = f"%{q.strip()}%" if q.strip() else None
    with connect() as conn:
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
    return rows, total


def get_concept(synset_id: str) -> dict[str, Any] | None:
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
    return {"synset": synset, "terms": {row["lang"]: row for row in terms}}
