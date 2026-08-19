from pathlib import Path

from warehouse.ingest.llm_gaps import (
    accept_llm_lemma,
    backtranslate_ok,
    load_gap_cache,
    may_write_llm,
    missing_rank_slots,
    propose_lemma,
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
