"""
tests/test_golden_benchmark.py

Golden Benchmark Test Suite for Tier 1 Core Vocabulary.
Verifies that foundational high-frequency concepts are translated accurately,
naturally, and without ambiguity across Vietnamese, Chinese, and English.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
import pytest

OUT_DIR = Path(__file__).resolve().parents[1] / "out"
UNION_PATH = OUT_DIR / "core_vocabulary.json.gz"
OVERRIDES_FILE = Path(__file__).resolve().parents[1] / "warehouse" / "curated_overrides.json"


def load_catalog(path: Path) -> dict:
    assert path.exists(), f"Missing export catalog: {path}"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def load_golden_set() -> dict[str, dict[str, str]]:
    assert OVERRIDES_FILE.exists(), f"Missing overrides: {OVERRIDES_FILE}"
    return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalog() -> dict:
    return load_catalog(UNION_PATH)


@pytest.fixture(scope="module")
def golden_set() -> dict[str, dict[str, str]]:
    return load_golden_set()


def test_golden_benchmark_accuracy(catalog: dict, golden_set: dict[str, dict[str, str]]) -> None:
    concepts_by_id = {c["id"]: c for c in catalog["concepts"]}
    
    total_checks = 0
    passed_checks = 0
    failures = []

    for synset_id, expected_terms in golden_set.items():
        if synset_id not in concepts_by_id:
            failures.append(f"Concept {synset_id} missing from catalog")
            continue
        
        concept = concepts_by_id[synset_id]
        for lang, expected_text in expected_terms.items():
            total_checks += 1
            actual_text = concept["terms"].get(lang, {}).get("text")
            if actual_text == expected_text:
                passed_checks += 1
            else:
                failures.append(
                    f"[{synset_id}][{lang}] Expected: '{expected_text}', Actual: '{actual_text}'"
                )

    accuracy = (passed_checks / total_checks) * 100 if total_checks > 0 else 0
    assert accuracy == 100.0, f"Golden Benchmark Failed with {len(failures)} mismatches ({accuracy:.1f}% accuracy):\n" + "\n".join(failures[:10])


def test_no_empty_meanings_in_golden_concepts(catalog: dict, golden_set: dict[str, dict[str, str]]) -> None:
    concepts_by_id = {c["id"]: c for c in catalog["concepts"]}
    for synset_id in golden_set:
        if synset_id in concepts_by_id:
            meaning = concepts_by_id[synset_id].get("meaning", "").strip()
            assert len(meaning) > 0, f"Concept {synset_id} has empty meaning"
