# /Users/admin/Documents/big-data/tests/test_pedagogical_syllabus.py
from warehouse.pedagogical_syllabus import generate_pedagogical_syllabus

def test_syllabus_contains_top_learner_words():
    syllabus = generate_pedagogical_syllabus(top_n=1000)
    words = {c["word"] for c in syllabus}
    assert "water" in words
    assert "learn" in words
    assert "study" in words
    assert "can" in words
    assert "must" in words
    assert "even" in words
    assert "the" not in words
    assert "of" not in words
    assert len(syllabus) == 1000
