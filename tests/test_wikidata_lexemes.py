from pathlib import Path

from warehouse.download_sources import DATA_SOURCES
from warehouse.ingest.wikidata_lexemes import parse_p8814, wikidata_lexeme_links


def test_parse_p8814():
    assert parse_p8814("00007846-n") == (7846, "noun")
    assert parse_p8814("bad") is None


def test_lexeme_links_via_p8814():
    entity = {
        "type": "lexeme",
        "lemmas": {"vi": {"value": "nước"}},
        "claims": {
            "P8814": [{"mainsnak": {"datavalue": {"value": "00007846-n"}}}]
        },
    }
    offset_index = {(7846, "noun"): "water.n.01"}
    assert wikidata_lexeme_links(entity, offset_index) == [("water.n.01", "vi", "nước")]


def test_lexeme_without_wordnet_id_is_skipped():
    entity = {"type": "lexeme", "lemmas": {"vi": {"value": "nước"}}, "claims": {}}
    assert wikidata_lexeme_links(entity, {}) == []


def test_wikidata_lexemes_source_is_registered():
    spec = DATA_SOURCES["wikidata-lexemes"]
    assert "latest-lexemes.json.gz" in spec["filename"]
    assert spec["extract"] is False


def test_schema_sql_declares_wikidata_and_llm_sources():
    sql = Path("sql/001_schema.sql").read_text(encoding="utf-8")
    assert "('wikidata'" in sql
    assert "('llm'" in sql
