"""
warehouse/pedagogical_syllabus.py

Modern Oxford/CEFR pedagogical syllabus generator.
Extracts clean, high-frequency, unambiguous learner headwords from wordfreq modern English corpus.
"""

from __future__ import annotations

from typing import Any
import wordfreq
from schema import FUNCTION_WORDS, LEARNER_CORE_ENGLISH

STOPWORDS = FUNCTION_WORDS - LEARNER_CORE_ENGLISH


def generate_pedagogical_syllabus(top_n: int = 6000) -> list[dict[str, Any]]:
    """Extract top N clean learner headwords from modern English corpora."""
    raw_words = wordfreq.top_n_list("en", top_n * 3)
    syllabus: list[dict[str, Any]] = []
    seen: set[str] = set()
    rank = 1

    for w in raw_words:
        w_lower = w.strip().lower()
        if len(w_lower) < 2 and w_lower not in ("i", "a"):
            continue
        if w_lower in STOPWORDS or w_lower in seen:
            continue
        if not w_lower.isalpha():
            continue

        seen.add(w_lower)
        concept_id = f"{w_lower}.core.{rank:04d}"
        syllabus.append({
            "id": concept_id,
            "word": w_lower,
            "rank": rank,
        })
        rank += 1
        if len(syllabus) >= top_n:
            break

    return syllabus
