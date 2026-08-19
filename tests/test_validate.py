from __future__ import annotations

import copy
from typing import Any

import pytest

from phonology import phonology_dto
from schema import LANGUAGES
from validate import ValidationError, validate_document


def good_document() -> dict[str, Any]:
    return {
        "version": 1,
        "generatedAt": "2026-08-17T00:00:00Z",
        "sources": ["wordfreq", "omw-1.4", "wiktextract"],
        "languages": list(LANGUAGES),
        "phonology": phonology_dto(LANGUAGES),
        "topN": 12000,
        "count": 2,
        "concepts": [
            {
                "id": "eat.v.01",
                "pos": "verb",
                "meaning": "take in solid food",
                "terms": {
                    "en": {"text": "eat", "rank": 2, "readings": {"ipa": "/iːt/"}},
                    "vi": {"text": "ăn", "rank": 1},
                    "zh": {"text": "吃", "rank": 1, "readings": {"pinyin": "chī", "zhuyin": "ㄔ"}},
                },
            },
            {
                "id": "water.n.01",
                "pos": "noun",
                "meaning": "a clear liquid essential for life",
                "terms": {"en": {"text": "water", "rank": 1}, "vi": {"text": "nước", "rank": 2}},
            },
        ],
    }


def test_accepts_valid_document() -> None:
    warnings, coverage = validate_document(good_document())
    assert warnings == []
    assert coverage["en"] == 2
    assert coverage["vi"] == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc["concepts"][0].__setitem__("rank", 1),
        lambda doc: doc["concepts"][0]["terms"].__setitem__("fr", {"text": "", "rank": 1}),
        lambda doc: doc["concepts"][0]["terms"]["vi"].__delitem__("rank"),
        lambda doc: doc["concepts"][0]["terms"].__setitem__("vi", {"text": "ăn", "rank": 1, "readings": {"bogus": "x"}}),
        lambda doc: doc.__setitem__("count", 99),
    ],
)
def test_rejects_bad_documents(mutate) -> None:
    doc = copy.deepcopy(good_document())
    mutate(doc)
    with pytest.raises(ValidationError):
        validate_document(doc)


def test_rejects_duplicate_ranks_within_language() -> None:
    doc = copy.deepcopy(good_document())
    doc["concepts"][0]["terms"]["vi"]["rank"] = 2
    with pytest.raises(ValidationError):
        validate_document(doc)


def test_pivoted_document_requires_pivot_term() -> None:
    doc = copy.deepcopy(good_document())
    doc["pivot"] = "zh"
    doc["concepts"] = [doc["concepts"][0]]
    doc["count"] = 1
    doc["concepts"][0]["terms"]["zh"]["rank"] = 1
    warnings, coverage = validate_document(doc)
    assert coverage["zh"] == 1
