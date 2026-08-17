from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import Any

from warehouse.config import OUT_DIR

CORE_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE concepts (
  id TEXT PRIMARY KEY,
  pos TEXT NOT NULL,
  meaning TEXT NOT NULL,
  meaning_lang TEXT NOT NULL DEFAULT 'en'
);
CREATE TABLE terms (
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  lang TEXT NOT NULL,
  text TEXT NOT NULL,
  rank INTEGER NOT NULL,
  readings TEXT,
  PRIMARY KEY (concept_id, lang)
);
CREATE INDEX idx_terms_lang_rank ON terms(lang, rank);
"""


def write_catalog_sqlite(catalog: dict[str, Any], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    conn = sqlite3.connect(dest)
    try:
        conn.executescript(CORE_SCHEMA)
        conn.execute("INSERT INTO meta(key, value) VALUES('version', ?)", (str(catalog.get("version", 1)),))
        conn.execute("INSERT INTO meta(key, value) VALUES('count', ?)", (str(catalog.get("count", 0)),))
        conn.execute("INSERT INTO meta(key, value) VALUES('topN', ?)", (str(catalog.get("topN", 0)),))
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('languages', ?)",
            (json.dumps(catalog.get("languages", []), ensure_ascii=False),),
        )
        if catalog.get("pivot"):
            conn.execute("INSERT INTO meta(key, value) VALUES('pivot', ?)", (str(catalog["pivot"]),))
        concepts = [
            (concept["id"], concept.get("pos") or "other", concept.get("meaning") or "", "en")
            for concept in catalog.get("concepts", [])
        ]
        conn.executemany("INSERT INTO concepts(id, pos, meaning, meaning_lang) VALUES(?,?,?,?)", concepts)
        terms: list[tuple[str, str, str, int, str | None]] = []
        for concept in catalog.get("concepts", []):
            for lang, term in (concept.get("terms") or {}).items():
                text = str(term.get("text") or "").strip()
                rank = int(term.get("rank") or 0)
                if not text or rank < 1:
                    continue
                readings = term.get("readings")
                terms.append(
                    (
                        concept["id"],
                        lang,
                        text,
                        rank,
                        json.dumps(readings, ensure_ascii=False) if readings else None,
                    )
                )
        conn.executemany(
            "INSERT OR REPLACE INTO terms(concept_id, lang, text, rank, readings) VALUES(?,?,?,?,?)",
            terms,
        )
        conn.commit()
    finally:
        conn.close()
    return dest


def export_sqlite(
    out_dir: Path | None = None,
    top_n: int = 12000,
    pivot: str | None = None,
    from_json: Path | None = None,
) -> Path:
    dest_dir = out_dir or OUT_DIR
    if from_json is not None:
        if from_json.suffix == ".gz":
            catalog = json.loads(gzip.decompress(from_json.read_bytes()).decode("utf-8"))
        else:
            catalog = json.loads(from_json.read_text(encoding="utf-8"))
    else:
        from warehouse.export_json import build_catalog

        catalog = build_catalog(top_n=top_n, pivot=pivot)
    stem = f"lexicon-core.{pivot}-{top_n}" if pivot else "lexicon-core"
    path = dest_dir / f"{stem}.db"
    write_catalog_sqlite(catalog, path)
    gz_path = dest_dir / f"{stem}.db.gz"
    gz_path.write_bytes(gzip.compress(path.read_bytes(), compresslevel=9))
    print(f"exported {path} concepts={catalog.get('count')} gz={gz_path.stat().st_size}")
    return path
