from warehouse.generate_all_glosses import (
    collect_pending,
    fill_english_glosses,
    missing_langs,
    pack_by_slots,
)


def _concept(cid: str, langs: list[str], meaning: str = "a clock") -> dict:
    return {
        "id": cid,
        "pos": "n",
        "meaning": meaning,
        "terms": {lang: {"text": lang} for lang in langs},
    }


def test_english_is_copied_not_requested():
    concepts = [_concept("time.n.01", ["en", "vi", "zh"])]
    cache: dict = {}
    assert fill_english_glosses(concepts, cache) == 1
    assert cache["time.n.01"]["en"] == "a clock"
    assert missing_langs(concepts[0], None, cache) == ["vi", "zh"]


def test_complete_concepts_are_skipped():
    catalog = {
        "concepts": [
            _concept("a.n.01", ["en", "vi"]),
            _concept("b.n.01", ["en", "vi"]),
        ]
    }
    cache = {
        "a.n.01": {"en": "one", "vi": "một"},
        "b.n.01": {"en": "two"},
    }
    pending = collect_pending(catalog, None, cache)
    assert [c["id"] for c, _ in pending] == ["b.n.01"]
    assert pending[0][1] == ["vi"]


def test_pack_by_slots_respects_budget():
    pending = [(_concept(f"c{i}.n.01", ["vi", "zh", "ja"]), ["vi", "zh", "ja"]) for i in range(5)]
    batches = pack_by_slots(pending, slot_budget=6)
    assert [len(b) for b in batches] == [2, 2, 1]
    assert sum(len(item[1]) for b in batches for item in b) == 15
