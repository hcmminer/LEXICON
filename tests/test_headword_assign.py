from warehouse.headword_assign import assign_unique_headwords, drop_bound_fragments, is_learner_headword


def test_rejects_function_phrases_and_affixes():
    assert not is_learner_headword("de", "die und die")
    assert not is_learner_headword("de", "und, und, und")
    assert not is_learner_headword("de", "aus-")
    assert is_learner_headword("de", "Sonne")
    assert is_learner_headword("vi", "chương trình")
    assert is_learner_headword("zh", "球场")


def test_drops_bound_syllable_when_compound_exists():
    kept = drop_bound_fragments(
        [
            {"lemma_id": 1, "text": "trình", "score": 6.1},
            {"lemma_id": 2, "text": "chương trình", "score": 5.6},
        ]
    )
    assert [item["text"] for item in kept] == ["chương trình"]


def test_unique_assignment_prefers_unused_lemma():
    synsets = ["china.n.01", "court.n.01"]
    candidates = {
        ("china.n.01", "zh"): [
            {"lemma_id": 1, "text": "中国", "score": 9.0},
        ],
        ("court.n.01", "zh"): [
            {"lemma_id": 1, "text": "中国", "score": 8.0},
            {"lemma_id": 2, "text": "球场", "score": 7.0},
        ],
    }
    got = assign_unique_headwords(synsets, ("zh",), candidates, max_uses=1)
    assert got[("china.n.01", "zh")]["text"] == "中国"
    assert got[("court.n.01", "zh")]["text"] == "球场"


def test_max_uses_two_allows_one_repeat():
    synsets = ["a.n.01", "b.n.01", "c.n.01"]
    candidates = {
        ("a.n.01", "en"): [{"lemma_id": 1, "text": "bank", "score": 9.0}],
        ("b.n.01", "en"): [{"lemma_id": 1, "text": "bank", "score": 8.0}],
        ("c.n.01", "en"): [
            {"lemma_id": 1, "text": "bank", "score": 7.0},
            {"lemma_id": 2, "text": "shore", "score": 6.0},
        ],
    }
    got = assign_unique_headwords(synsets, ("en",), candidates, max_uses=2)
    assert got[("a.n.01", "en")]["text"] == "bank"
    assert got[("a.n.01", "en")]["text"] == "bank"
    assert got[("b.n.01", "en")]["text"] == "bank"
    assert got[("c.n.01", "en")]["text"] == "shore"
