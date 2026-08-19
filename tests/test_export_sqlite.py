from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from warehouse.export_sqlite import write_catalog_sqlite


def test_write_catalog_sqlite_slices_by_rank(tmp_path: Path) -> None:
    dest = tmp_path / "lexicon-core.db"
    write_catalog_sqlite(
        {
            "version": 1,
            "count": 2,
            "topN": 2,
            "languages": ["zh", "vi"],
            "concepts": [
                {
                    "id": "water.n.01",
                    "pos": "noun",
                    "meaning": "a liquid",
                    "terms": {
                        "zh": {"text": "水", "rank": 1},
                        "vi": {"text": "nước", "rank": 2},
                    },
                },
                {
                    "id": "eat.v.01",
                    "pos": "verb",
                    "meaning": "take food",
                    "terms": {"zh": {"text": "吃", "rank": 4}},
                },
            ],
        },
        dest,
    )
    conn = sqlite3.connect(dest)
    ids = [
        row[0]
        for row in conn.execute(
            "SELECT concept_id FROM terms WHERE lang = ? AND rank <= ? ORDER BY rank",
            ("zh", 2),
        )
    ]
    assert ids == ["water.n.01"]
    assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 2
    conn.close()


def test_schema_has_rank_index() -> None:
    dest = Path("/tmp/lexicon-core-schema-test.db")
    if dest.exists():
        dest.unlink()
    write_catalog_sqlite(
        {
            "version": 1,
            "count": 1,
            "topN": 1,
            "languages": ["en", "vi"],
            "concepts": [
                {
                    "id": "water.n.01",
                    "pos": "noun",
                    "meaning": "a liquid",
                    "terms": {"en": {"text": "water", "rank": 1}, "vi": {"text": "nước", "rank": 1}},
                }
            ],
        },
        dest,
    )
    conn = sqlite3.connect(dest)
    index_names = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert "idx_terms_lang_rank" in index_names
    conn.close()
    dest.unlink(missing_ok=True)


def test_round_trip_readings_are_json() -> None:
    dest = Path("/tmp/lexicon-core-readings-test.db")
    if dest.exists():
        dest.unlink()
    write_catalog_sqlite(
        {
            "version": 1,
            "count": 1,
            "topN": 1,
            "languages": ["zh"],
            "concepts": [
                {
                    "id": "water.n.01",
                    "pos": "noun",
                    "meaning": "a liquid",
                    "terms": {"zh": {"text": "水", "rank": 1, "readings": {"pinyin": "shuǐ"}}},
                }
            ],
        },
        dest,
    )
    conn = sqlite3.connect(dest)
    row = conn.execute("SELECT readings FROM terms WHERE lang = 'zh'").fetchone()
    assert row is not None
    assert json.loads(row[0]) == {"pinyin": "shuǐ"}
    conn.close()
    dest.unlink(missing_ok=True)
