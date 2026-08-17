from __future__ import annotations

from warehouse.db import connect, executemany


def ingest_readings(limit: int | None = None) -> None:
    from warehouse.build_readings import readings_for

    sql = """
        SELECT id, lang, text
        FROM core.lemmas
        WHERE lang = ANY(%s)
        ORDER BY id
    """
    langs = ["en", "zh", "ja", "ko"]
    params: list = [langs]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    count = 0
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        batch = []
        for row in rows:
            for system, value in readings_for(row["lang"], row["text"]).items():
                batch.append((row["id"], system, value, "readings"))
            if len(batch) >= 2000:
                executemany(conn,
                    """
                    INSERT INTO core.readings (lemma_id, system, value, source_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    batch,
                )
                count += len(batch)
                batch.clear()
                conn.commit()
        if batch:
            executemany(conn,
                """
                INSERT INTO core.readings (lemma_id, system, value, source_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                batch,
            )
            count += len(batch)
        conn.execute(
            """
            INSERT INTO core.ingest_runs (source_id, finished_at, row_count)
            VALUES ('readings', now(), %s)
            """,
            (count,),
        )
        conn.commit()
    print(f"readings {count}")
