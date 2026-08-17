from __future__ import annotations

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
