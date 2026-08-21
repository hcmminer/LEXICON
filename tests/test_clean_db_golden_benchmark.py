# /Users/admin/Documents/big-data/tests/test_clean_db_golden_benchmark.py
import sqlite3
from pathlib import Path
from warehouse.config import OUT_DIR


def test_clean_db_has_exact_core_translations():
    db_path = OUT_DIR / "lexicon-core.db"
    assert db_path.exists(), "lexicon-core.db must exist"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    expected_pairs = [
        ("learn", "vi", "học"),
        ("must", "vi", "phải"),
        ("can", "vi", "có thể"),
        ("water", "vi", "nước"),
        ("home", "vi", "nhà"),
        ("grandfather", "vi", "ông"),
        ("impossible", "vi", "không thể"),
        ("sometimes", "vi", "thỉnh thoảng"),
        ("even", "vi", "thậm chí"),
        ("number", "vi", "số"),
        ("main", "vi", "chính"),
        ("right", "vi", "đúng"),
    ]
    for en_word, lang, expected_trans in expected_pairs:
        cur.execute("""
            SELECT t.text FROM terms t
            JOIN terms e ON e.concept_id = t.concept_id AND e.lang = 'en'
            WHERE e.text = ? AND t.lang = ?
        """, (en_word, lang))
        rows = [r[0] for r in cur.fetchall()]
        assert expected_trans in rows, f"Missing {expected_trans} for {en_word} in {lang}. Found: {rows}"
    conn.close()
