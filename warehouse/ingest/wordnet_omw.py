from __future__ import annotations

import os
from pathlib import Path

from schema import OMW_LANG_TO_ISO, WORDNET_POS_TO_OURS
from warehouse.config import CACHE
from warehouse.db import connect, executemany
from warehouse.download_sources import ensure_data_source
from warehouse.textutil import clean_lemma, is_usable_lemma, normalize, script_ok

NLTK_DATA = CACHE / "nltk_data"


def _ensure_nltk() -> None:
    ensure_data_source("wordnet")
    ensure_data_source("omw")
    os.environ.setdefault("NLTK_DATA", str(NLTK_DATA))
    import nltk

    if str(NLTK_DATA) not in nltk.data.path:
        nltk.data.path.insert(0, str(NLTK_DATA))


def _upsert_lemma(conn, lang: str, text: str) -> int | None:
    if not is_usable_lemma(text) or not script_ok(lang, text):
        return None
    row = conn.execute(
        """
        INSERT INTO core.lemmas (lang, text, normalized)
        VALUES (%s, %s, %s)
        ON CONFLICT (lang, normalized) DO UPDATE SET text = EXCLUDED.text
        RETURNING id
        """,
        (lang, text, normalize(text)),
    ).fetchone()
    return None if row is None else int(row["id"])


def ingest_wordnet() -> None:
    _ensure_nltk()
    from nltk.corpus import wordnet as wn

    synsets = []
    lemma_rows = {}
    links = []
    for synset in wn.all_synsets():
        meaning = synset.definition().strip()
        if not meaning:
            continue
        pos = synset.pos()
        if pos not in WORDNET_POS_TO_OURS:
            continue
        synsets.append((synset.name(), synset.offset(), pos, meaning))
        for name in synset.lemma_names("eng"):
            lemma = clean_lemma(name)
            if not is_usable_lemma(lemma) or not script_ok("en", lemma):
                continue
            lemma_rows[normalize(lemma)] = lemma
            links.append((synset.name(), normalize(lemma)))

    with connect() as conn:
        executemany(conn,
            """
            INSERT INTO core.synsets (id, wn_offset, pos, definition_en)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET definition_en = EXCLUDED.definition_en
            """,
            synsets,
        )
        executemany(conn,
            """
            INSERT INTO core.lemmas (lang, text, normalized)
            VALUES ('en', %s, %s)
            ON CONFLICT (lang, normalized) DO NOTHING
            """,
            [(text, norm) for norm, text in lemma_rows.items()],
        )
        executemany(conn,
            """
            INSERT INTO core.sense_lemmas (synset_id, lemma_id, source_id)
            SELECT %s, l.id, 'wordnet'
            FROM core.lemmas l
            WHERE l.lang = 'en' AND l.normalized = %s
            ON CONFLICT DO NOTHING
            """,
            links,
        )
        conn.execute(
            """
            INSERT INTO core.ingest_runs (source_id, finished_at, row_count)
            VALUES ('wordnet', now(), %s)
            """,
            (len(synsets),),
        )
        conn.commit()
    print(f"wordnet synsets {len(synsets)} en-links {len(links)}")


def ingest_omw() -> None:
    root = NLTK_DATA / "corpora" / "omw-1.4"
    if not root.exists():
        raise SystemExit(f"OMW not found at {root}. Run the old build.py once or download OMW.")

    with connect() as conn:
        offset_index = {
            (row["wn_offset"], row["pos"]): row["id"]
            for row in conn.execute("SELECT id, wn_offset, pos FROM core.synsets")
        }
        count = 0
        for tab in sorted(root.rglob("wn-data-*.tab")):
            omw_lang = tab.stem.removeprefix("wn-data-")
            iso = OMW_LANG_TO_ISO.get(omw_lang)
            if iso is None:
                continue
            lemmas: dict[str, str] = {}
            links: list[tuple[str, str]] = []
            with tab.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 3:
                        continue
                    kind = parts[1]
                    if kind != "lemma" and not kind.endswith(":lemma"):
                        continue
                    try:
                        offset_s, pos = parts[0].rsplit("-", 1)
                        offset = int(offset_s)
                    except ValueError:
                        continue
                    synset_id = offset_index.get((offset, pos))
                    if synset_id is None and pos == "a":
                        synset_id = offset_index.get((offset, "s"))
                    if synset_id is None:
                        continue
                    lemma = clean_lemma(parts[2].replace("+", ""))
                    if not is_usable_lemma(lemma) or not script_ok(iso, lemma):
                        continue
                    norm = normalize(lemma)
                    lemmas[norm] = lemma
                    links.append((synset_id, norm))
            if lemmas:
                executemany(
                    conn,
                    """
                    INSERT INTO core.lemmas (lang, text, normalized)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (lang, normalized) DO NOTHING
                    """,
                    [(iso, text, norm) for norm, text in lemmas.items()],
                )
                executemany(
                    conn,
                    """
                    INSERT INTO core.sense_lemmas (synset_id, lemma_id, source_id)
                    SELECT %s, l.id, 'omw-1.4'
                    FROM core.lemmas l
                    WHERE l.lang = %s AND l.normalized = %s
                    ON CONFLICT DO NOTHING
                    """,
                    [(synset_id, iso, norm) for synset_id, norm in links],
                )
            conn.commit()
            count += len(links)
            print(f"  omw {iso}: {len(links)}")
        conn.execute(
            """
            INSERT INTO core.ingest_runs (source_id, finished_at, row_count)
            VALUES ('omw-1.4', now(), %s)
            """,
            (count,),
        )
        conn.commit()
    print(f"omw sense_lemmas {count}")
