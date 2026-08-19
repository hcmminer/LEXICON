import sqlite3
from pathlib import Path

from schema import LANGUAGES
from warehouse.export_sqlite import write_catalog_sqlite


def test_full_matrix_export_has_every_language():
    langs = list(LANGUAGES)
    concepts = []
    for i in range(3):
        terms = {
            lang: {"text": f"w{i}-{lang}" if lang != "zh" else "水", "rank": i + 1, "meaning": "m"}
            for lang in langs
        }
        terms["zh"]["text"] = "水"
        terms["ja"]["text"] = "水"
        terms["ko"]["text"] = "물"
        terms["ar"]["text"] = "ماء"
        terms["he"]["text"] = "מים"
        terms["hi"]["text"] = "पानी"
        terms["bn"]["text"] = "জল"
        terms["ta"]["text"] = "நீர்"
        terms["te"]["text"] = "నీరు"
        terms["th"]["text"] = "น้ำ"
        terms["ru"]["text"] = "вода"
        terms["uk"]["text"] = "вода"
        terms["el"]["text"] = "νερό"
        terms["vi"]["text"] = "nước"
        concepts.append({"id": f"c{i}.n.01", "pos": "noun", "meaning": "x", "terms": terms})
    dest = write_catalog_sqlite(
        {"version": 1, "count": 3, "topN": 3, "languages": langs, "concepts": concepts},
        Path("/tmp/coverage-gate.db"),
    )
    conn = sqlite3.connect(dest)
    counts = dict(conn.execute("SELECT lang, COUNT(*) FROM terms GROUP BY lang"))
    conn.close()
    dest.unlink(missing_ok=True)
    assert set(counts) == set(langs)
    assert all(n == 3 for n in counts.values())
