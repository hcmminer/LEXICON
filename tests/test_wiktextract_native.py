from urllib.parse import quote

from schema import LANGUAGES
from warehouse.download_sources import DATA_SOURCES
from warehouse.ingest.wiktextract_native import KAIKKI_NATIVE_LANGS, native_entry_links


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


def test_native_entry_maps_via_sense_links():
    en_index = {("sew", "verb"): ["sew.v.01"]}
    entry = {
        "word": "may",
        "lang_code": "vi",
        "pos": "verb",
        "senses": [{"glosses": ["to sew"], "links": [["sew", "sew"]]}],
    }
    assert native_entry_links(entry, en_index) == [("sew.v.01", "vi", "may")]


def test_every_non_english_language_has_a_kaikki_dump_spec():
    missing = [lang for lang in LANGUAGES if lang != "en" and lang not in KAIKKI_NATIVE_LANGS]
    assert missing == []
    for lang, name in KAIKKI_NATIVE_LANGS.items():
        key = f"kaikki-{lang}"
        assert key in DATA_SOURCES
        url = DATA_SOURCES[key]["urls"][0]
        assert quote(name) in url or name in url
