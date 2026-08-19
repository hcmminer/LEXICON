"""
Data-quality gates for the exported catalog.

These run against the real exported artifacts (no Postgres needed) so a bad
re-rank / re-export is caught before it ships to the extension.

Thresholds are evidence-based from the specificity + stoplist work:
  * every catalog must pass the schema validator;
  * no headword may be a known function word;
  * the share of concepts whose headword (any language) is an extremely
    ambiguous lemma (>= 4 synsets across the union) must stay bounded;
  * known-bad OMW/wiktextract translations must not regress.

Run:  .venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path

import pytest

from schema import FUNCTION_WORDS, FUNCTION_WORDS_BY_LANG
from validate import validate_document

OUT_DIR = Path(__file__).resolve().parents[1] / "out"
UNION_PATH = OUT_DIR / "core_vocabulary.json.gz"
PIVOT_PATH = OUT_DIR / "core_vocabulary.zh-3000.json.gz"

# One concept is legitimately polysemous in many languages ("ăn", "keep").
# The guard we ship is: the share of concepts touched by a headword that maps
# to >= 4 synsets across the whole union stays under 70% (measured 62.2%).
HIGH_AMBIGUITY_SYNSETS = 4
HIGH_AMBIGUITY_CONCEPT_RATIO_MAX = 0.70


def load_catalog(path: Path) -> dict:
    assert path.exists(), f"missing export artifact {path} — run the export first"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def headword_spans(catalog: dict) -> dict[tuple[str, str], list[str]]:
    spans: dict[tuple[str, str], list[str]] = defaultdict(list)
    for concept in catalog["concepts"]:
        for lang, term in concept["terms"].items():
            spans[(lang, term["text"])].append(concept["id"])
    return spans


@pytest.fixture(scope="module")
def union() -> dict:
    return load_catalog(UNION_PATH)


@pytest.fixture(scope="module")
def pivot() -> dict:
    return load_catalog(PIVOT_PATH)


def test_union_schema_is_valid(union: dict) -> None:
    warnings, coverage = validate_document(union)
    assert warnings == []
    assert coverage["en"] == union["count"]


def test_pivot_schema_is_valid(pivot: dict) -> None:
    warnings, coverage = validate_document(pivot)
    assert warnings == []
    assert coverage["zh"] == pivot["count"]


@pytest.mark.parametrize("fixture_name", ["union", "pivot"])
def test_no_function_word_headwords(request, fixture_name: str) -> None:
    catalog = request.getfixturevalue(fixture_name)
    stop_by_lang: dict[str, set[str]] = {"en": set(FUNCTION_WORDS)}
    for lang, words in FUNCTION_WORDS_BY_LANG.items():
        stop_by_lang.setdefault(lang, set()).update(words)
    offenders = []
    for concept in catalog["concepts"]:
        for lang, term in concept["terms"].items():
            if term["text"] in stop_by_lang.get(lang, set()):
                offenders.append((concept["id"], lang, term["text"]))
    assert offenders == [], f"function-word headwords leaked: {offenders[:10]}"


def test_ambiguous_headwords_stay_bounded(union: dict) -> None:
    spans = headword_spans(union)
    touched: set[str] = set()
    for span in spans.values():
        if len(span) >= HIGH_AMBIGUITY_SYNSETS:
            touched.update(span)
    ratio = len(touched) / union["count"]
    assert ratio < HIGH_AMBIGUITY_CONCEPT_RATIO_MAX, (
        f"high-ambiguity headword coverage {ratio:.1%} exceeds "
        f"{HIGH_AMBIGUITY_CONCEPT_RATIO_MAX:.0%}"
    )


def test_known_bad_translations_do_not_regress(union: dict) -> None:
    by_id = {concept["id"]: concept for concept in union["concepts"]}
    preserve = by_id.get("preserve.v.04")
    assert preserve is not None, "preserve.v.04 missing from union"
    vi_term = preserve["terms"].get("vi", {}).get("text")
    assert vi_term not in (None, "cứ"), f"preserve.v.04 vi regressed to {vi_term!r}"


def test_pivot_has_no_known_noisy_headwords(pivot: dict) -> None:
    noisy = {"cứ", "loạt"}
    offenders = []
    for concept in pivot["concepts"]:
        for lang, term in concept["terms"].items():
            if term["text"] in noisy:
                offenders.append((concept["id"], lang, term["text"]))
    assert offenders == [], f"noisy pivot headwords: {offenders[:10]}"


def test_vi_coverage_is_reasonable(union: dict) -> None:
    with_vi = sum(1 for concept in union["concepts"] if "vi" in concept["terms"])
    assert with_vi / union["count"] >= 0.30, f"vi coverage too low: {with_vi}/{union['count']}"
