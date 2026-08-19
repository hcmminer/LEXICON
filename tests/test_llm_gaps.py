from pathlib import Path

from warehouse.cli import INGEST_ONLY
from warehouse.ingest.llm_gaps import (
    accept_llm_lemma,
    backtranslate_ok,
    load_gap_cache,
    may_write_llm,
    missing_rank_slots,
    pack_gap_slots,
    propose_lemma,
    propose_lemmas_batch,
    save_gap_cache,
)


def test_missing_rank_slots_skips_filled_and_english():
    catalog = ["water.n.01", "eat.v.01"]
    ranked = {("water.n.01", "vi"), ("water.n.01", "en"), ("eat.v.01", "en")}
    missing = missing_rank_slots(ranked, catalog, ("en", "vi", "zh"))
    assert ("water.n.01", "en") not in missing
    assert ("water.n.01", "vi") not in missing
    assert ("water.n.01", "zh") in missing
    assert ("eat.v.01", "vi") in missing


def test_accept_and_backtranslate_and_gold_lock(tmp_path: Path):
    assert accept_llm_lemma("vi", "nước") == "nước"
    assert accept_llm_lemma("vi", "water") is None
    assert backtranslate_ok("water", {"water", "H2O"})
    assert not backtranslate_ok("chair", {"water"})
    assert may_write_llm(None)
    assert not may_write_llm("omw-1.4")
    path = tmp_path / "gaps.json"
    save_gap_cache(path, {"water.n.01\tvi": "nước"})
    assert load_gap_cache(path)["water.n.01\tvi"] == "nước"


def test_propose_lemma_accepts_valid_roundtrip():
    def fake_call(system, user, **kwargs):
        assert "water.n.01" in user
        return {"lemma": "nước", "back_en": "water"}

    assert (
        propose_lemma(
            "water.n.01",
            "noun",
            "a liquid",
            ["water"],
            "vi",
            [],
            call_json=fake_call,
        )
        == "nước"
    )


def test_pack_gap_slots_respects_budget():
    pending = [(f"c{i}.n.01", ["vi", "zh", "ja"]) for i in range(5)]
    batches = pack_gap_slots(pending, slot_budget=6)
    assert [sum(len(langs) for _, langs in batch) for batch in batches] == [6, 6, 3]


def test_propose_lemmas_batch_accepts_multi_synset():
    def fake_call(system, user, **kwargs):
        assert "water.n.01" in user
        assert "eat.v.01" in user
        return {
            "water.n.01": {"vi": {"lemma": "nước", "back_en": "water"}},
            "eat.v.01": {"vi": {"lemma": "ăn", "back_en": "eat"}, "zh": {"lemma": "eat", "back_en": "eat"}},
        }

    items = [
        {
            "id": "water.n.01",
            "pos": "noun",
            "meaning": "a liquid",
            "en_lemmas": ["water"],
            "langs": ["vi"],
        },
        {
            "id": "eat.v.01",
            "pos": "verb",
            "meaning": "take food",
            "en_lemmas": ["eat"],
            "langs": ["vi", "zh"],
        },
    ]
    got = propose_lemmas_batch(items, call_json=fake_call)
    assert got == {("water.n.01", "vi"): "nước", ("eat.v.01", "vi"): "ăn"}


def test_propose_lemmas_for_synset_accepts_valid_langs():
    from warehouse.ingest.llm_gaps import propose_lemmas_for_synset

    def fake_call(system, user, **kwargs):
        return {
            "vi": {"lemma": "nước", "back_en": "water"},
            "zh": {"lemma": "water", "back_en": "water"},
        }

    got = propose_lemmas_for_synset(
        "water.n.01",
        "noun",
        "a liquid",
        ["water"],
        ["vi", "zh"],
        call_json=fake_call,
    )
    assert got == {"vi": "nước"}


def test_propose_lemma_rejects_bad_backtranslate_then_none_on_second_fail():
    calls = {"n": 0}

    def fake_call(system, user, **kwargs):
        calls["n"] += 1
        return {"lemma": "nước", "back_en": "chair"}

    assert (
        propose_lemma(
            "water.n.01",
            "noun",
            "a liquid",
            ["water"],
            "vi",
            [],
            call_json=fake_call,
        )
        is None
    )
    assert calls["n"] == 2


def test_ops_and_cli_advertise_new_jobs():
    from warehouse.web import OPS

    names = {item[0] for item in OPS}
    assert {"wiktextract-native", "wikidata", "llm-gaps"} <= names


def test_ingest_only_includes_coverage_pipeline():
    assert "wiktextract-native" in INGEST_ONLY
    assert "wikidata" in INGEST_ONLY
    assert "llm-gaps" in INGEST_ONLY
