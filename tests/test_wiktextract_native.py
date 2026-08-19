from warehouse.ingest.wiktextract_native import native_entry_links


def test_native_entry_maps_via_english_translation():
    en_index = {("water", "noun"): ["water.n.01"]}
    entry = {
        "word": "nước",
        "lang_code": "vi",
        "pos": "noun",
        "senses": [{"translations": [{"code": "en", "word": "water"}]}],
    }
    assert native_entry_links(entry, en_index) == [("water.n.01", "vi", "nước")]


def test_native_entry_skips_unknown_english_and_bad_script():
    en_index = {("water", "noun"): ["water.n.01"]}
    unknown = {
        "word": "xyzzy",
        "lang_code": "vi",
        "pos": "noun",
        "senses": [{"translations": [{"code": "en", "word": "not-a-synset"}]}],
    }
    latin_as_vi = {
        "word": "water",
        "lang_code": "vi",
        "pos": "noun",
        "senses": [{"translations": [{"code": "en", "word": "water"}]}],
    }
    assert native_entry_links(unknown, en_index) == []
    assert native_entry_links(latin_as_vi, en_index) == []
