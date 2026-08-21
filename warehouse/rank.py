from __future__ import annotations

from warehouse.config import SQL_DIR
from warehouse.db import connect


def compute_ranks(top_n: int) -> None:
    sql = (SQL_DIR / "002_ranks.sql").read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute("TRUNCATE core.concept_ranks")
        conn.execute("SET LOCAL work_mem = '256MB'")
        conn.execute(sql, {"top_n": top_n})
        stats = conn.execute(
            """
            SELECT lang, COUNT(*) AS n, MAX(rank) AS max_rank
            FROM core.concept_ranks
            GROUP BY lang
            ORDER BY lang
            """
        ).fetchall()
        total = conn.execute("SELECT COUNT(DISTINCT synset_id) AS n FROM core.concept_ranks").fetchone()
        conn.commit()
    print(f"ranked catalog synsets={total['n']} topN={top_n}")
    for row in stats:
        print(f"  {row['lang']:4} {row['n']}")

