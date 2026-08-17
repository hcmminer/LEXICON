#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from schema import LANGUAGES, POS_VALUES, READING_KEYS, SCHEMA_VERSION, SYNSET_ID_RE

SYNSET_RE = re.compile(SYNSET_ID_RE)


class ValidationError(Exception):
    pass


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ValidationError(message)


def _validate_term(lang: str, term: Any, concept_id: str) -> int:
    prefix = f"{concept_id}.{lang}"
    _require(isinstance(term, dict), f"{prefix} must be an object {{text, rank, readings?}}")
    text = term.get("text")
    _require(isinstance(text, str) and text.strip() != "", f"{prefix}.text must be a non-empty string")
    _require(text == text.strip(), f"{prefix}.text has surrounding whitespace")
    rank = term.get("rank")
    _require(isinstance(rank, int) and rank >= 1, f"{prefix}.rank must be an integer >= 1")
    if "readings" in term:
        readings = term["readings"]
        _require(isinstance(readings, dict), f"{prefix}.readings must be an object")
        _require(len(readings) > 0, f"{prefix}.readings must be omitted when empty")
        for key, value in readings.items():
            _require(isinstance(key, str) and key.strip() != "", f"{prefix}.readings has empty key")
            _require(isinstance(value, str) and value.strip() != "", f"{prefix}.readings.{key} must be a non-empty string")
    return rank


def validate_document(data: Any) -> tuple[list[str], dict[str, int]]:
    warnings: list[str] = []
    _require(isinstance(data, dict), "root must be an object, not an array")
    _require(data.get("version") == SCHEMA_VERSION, f"version must be {SCHEMA_VERSION}")
    _require(isinstance(data.get("generatedAt"), str) and data["generatedAt"], "generatedAt is required")
    _require(isinstance(data.get("sources"), list) and data["sources"], "sources must be a non-empty array")
    _require(isinstance(data.get("topN"), int) and data["topN"] >= 1, "topN must be an integer >= 1")
    languages = data.get("languages")
    _require(languages == list(LANGUAGES), "languages must be the locked 35 ISO codes in order")
    reading_keys = data.get("readingKeys")
    _require(reading_keys == list(READING_KEYS), "readingKeys must match the published registry")
    concepts = data.get("concepts")
    _require(isinstance(concepts, list), "concepts must be an array")
    _require(data.get("count") == len(concepts), "count must equal concepts.length")
    _require(len(concepts) > 0, "concepts must not be empty")

    ids: list[str] = []
    coverage = {lang: 0 for lang in LANGUAGES}
    ranks_by_lang: dict[str, list[int]] = defaultdict(list)

    for index, concept in enumerate(concepts):
        _require(isinstance(concept, dict), f"concepts[{index}] must be an object")
        concept_id = concept.get("id")
        _require(isinstance(concept_id, str) and SYNSET_RE.match(concept_id), f"concepts[{index}].id is not a WordNet synset")
        ids.append(concept_id)
        _require("rank" not in concept, f"{concept_id} must not have a concept-level rank")
        pos = concept.get("pos")
        _require(pos in POS_VALUES, f"{concept_id}.pos is not allowed: {pos!r}")
        meaning = concept.get("meaning")
        _require(isinstance(meaning, str) and meaning.strip() != "", f"{concept_id}.meaning is required")
        for banned in ("category", "cefr", "hsk", "examples"):
            _require(banned not in concept, f"{concept_id} must not contain {banned}")
        terms = concept.get("terms")
        _require(isinstance(terms, dict) and terms, f"{concept_id}.terms must be a non-empty object")
        for lang, term in terms.items():
            _require(lang in coverage, f"{concept_id} has unknown language {lang!r}")
            rank = _validate_term(lang, term, concept_id)
            ranks_by_lang[lang].append(rank)
            coverage[lang] += 1
        _require("en" in terms, f"{concept_id} is missing terms.en")
        _require(len(terms) >= 2, f"{concept_id} needs en + at least one other language")

    _require(len(ids) == len(set(ids)), f"duplicate ids: {[i for i, n in Counter(ids).items() if n > 1]}")
    for lang, ranks in ranks_by_lang.items():
        _require(len(ranks) == len(set(ranks)), f"duplicate {lang} ranks")
        expected = list(range(1, len(ranks) + 1))
        if sorted(ranks) != expected:
            raise ValidationError(f"{lang} ranks must be the contiguous range 1..{len(ranks)}")

    return warnings, coverage


def write_coverage(path: Path, coverage: dict[str, int], total: int) -> None:
    report = {
        "total": total,
        "languages": {
            lang: {"filled": coverage[lang], "ratio": round(coverage[lang] / total, 4)}
            for lang in LANGUAGES
        },
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    if path.suffix == ".gz":
        import gzip

        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def self_test() -> None:
    good = {
        "version": 1,
        "generatedAt": "2026-08-17T00:00:00Z",
        "sources": ["wordfreq", "omw-1.4", "wiktextract"],
        "languages": list(LANGUAGES),
        "readingKeys": list(READING_KEYS),
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
                "terms": {
                    "en": {"text": "water", "rank": 1},
                    "vi": {"text": "nước", "rank": 2},
                },
            },
        ],
    }
    warnings, coverage = validate_document(good)
    assert warnings == []
    assert coverage["en"] == 2
    assert coverage["vi"] == 2

    global_rank = json.loads(json.dumps(good))
    global_rank["concepts"][0]["rank"] = 1
    try:
        validate_document(global_rank)
        raise AssertionError("expected concept-level rank to fail")
    except ValidationError:
        pass

    bad = json.loads(json.dumps(good))
    bad["concepts"][0]["terms"] = {"en": {"text": "eat", "rank": 1}}
    try:
        validate_document(bad)
        raise AssertionError("expected monolingual concept to fail")
    except ValidationError:
        pass

    empty_text = json.loads(json.dumps(good))
    empty_text["concepts"][0]["terms"]["fr"] = {"text": "", "rank": 1}
    try:
        validate_document(empty_text)
        raise AssertionError("expected empty text to fail")
    except ValidationError:
        pass

    missing_rank = json.loads(json.dumps(good))
    del missing_rank["concepts"][0]["terms"]["vi"]["rank"]
    try:
        validate_document(missing_rank)
        raise AssertionError("expected missing term rank to fail")
    except ValidationError:
        pass

    print("self-test ok")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a core vocabulary catalog")
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--coverage-out", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.path is None:
        parser.error("path is required unless --self-test")

    try:
        data = load_json(args.path)
        warnings, coverage = validate_document(data)
    except ValidationError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 1

    print(f"VALID  concepts={data['count']} topN={data['topN']}")
    for lang in LANGUAGES:
        print(f"  {lang:4} {coverage[lang]}")
    for warning in warnings:
        print(f"WARN  {warning}")
    if args.coverage_out:
        write_coverage(args.coverage_out, coverage, data["count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
