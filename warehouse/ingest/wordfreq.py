from __future__ import annotations

from schema import LANGUAGES
from warehouse.db import connect, executemany
from warehouse.textutil import freq_lang, is_usable_lemma, normalize, script_ok


def ingest_wordfreq(limit_per_lang: int | None = None) -> None:
    from wordfreq import top_n_list, zipf_frequency

    from warehouse.ingest.seed import seed_reference_data

    seed_reference_data()
    cap = limit_per_lang or 40_000
    total = 0
    with connect() as conn:
        for lang in LANGUAGES:
            row = conn.execute(
                "SELECT has_wordlist, wordfreq_code FROM core.languages WHERE code = %s",
                (lang,),
            ).fetchone()
            if row is None or not row["has_wordlist"]:
                print(f"  wordfreq skip {lang}")
                continue
            words = top_n_list(row["wordfreq_code"], cap)
            batch = []
            rank = 0
            for word in words:
                if not is_usable_lemma(word) or not script_ok(lang, word):
                    continue
                rank += 1
                try:
                    score = zipf_frequency(word, row["wordfreq_code"])
                except Exception:
                    score = None
                batch.append((lang, word, normalize(word), score, rank))
            executemany(conn,
                """
                INSERT INTO core.lemmas (lang, text, normalized, zipf, wordfreq_rank)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (lang, normalized) DO UPDATE
                SET text = EXCLUDED.text,
                    zipf = EXCLUDED.zipf,
                    wordfreq_rank = EXCLUDED.wordfreq_rank
                """,
                batch,
            )
            conn.commit()
            total += len(batch)
            print(f"  wordfreq {lang}: {len(batch)}")
        conn.execute(
            """
            INSERT INTO core.ingest_runs (source_id, finished_at, row_count)
            VALUES ('wordfreq', now(), %s)
            """,
            (total,),
        )
        conn.commit()
    print(f"wordfreq lemmas {total}")
