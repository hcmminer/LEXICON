from warehouse.textutil import is_affix_lemma, is_usable_lemma


def test_rejects_hyphen_affixes():
    assert not is_usable_lemma("aus-")
    assert not is_usable_lemma("-ness")
    assert not is_usable_lemma("中-")
    assert not is_usable_lemma("non-")
    assert is_affix_lemma("aus-")
    assert is_affix_lemma("-heit")


def test_rejects_abbreviations_with_period():
    assert not is_usable_lemma("So.")
    assert not is_usable_lemma("e.g.")
    assert not is_usable_lemma("approx.")


def test_rejects_digits_and_empty():
    assert not is_usable_lemma("A1")
    assert not is_usable_lemma("Ａ型")
    assert not is_usable_lemma("")
    assert not is_usable_lemma("   ")


def test_sqlite_seed_has_no_affix_or_abbrev_headwords(tmp_path):
    from warehouse.export_sqlite import write_catalog_sqlite
    import sqlite3

    dest = tmp_path / "clean.db"
    write_catalog_sqlite(
        {
            "version": 1,
            "count": 2,
            "topN": 2,
            "languages": ["en", "de", "zh"],
            "concepts": [
                {
                    "id": "a.n.01",
                    "pos": "noun",
                    "meaning": "ok",
                    "terms": {
                        "en": {"text": "water", "rank": 1, "meaning": "a liquid"},
                        "de": {"text": "aus-", "rank": 1, "meaning": "prefix"},
                        "zh": {"text": "中-", "rank": 1, "meaning": "prefix"},
                    },
                }
            ],
        },
        dest,
    )
    conn = sqlite3.connect(dest)
    texts = [row[0] for row in conn.execute("SELECT text FROM terms")]
    conn.close()
    assert "aus-" not in texts
    assert "中-" not in texts
    assert "water" in texts


def test_keeps_normal_learner_words():
    assert is_usable_lemma("water")
    assert is_usable_lemma("chương trình")
    assert is_usable_lemma("中国")
    assert is_usable_lemma("Wasser")
    assert is_usable_lemma("lập trình")
