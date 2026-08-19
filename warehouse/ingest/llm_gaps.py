from __future__ import annotations

import json
from pathlib import Path

from warehouse.textutil import is_usable_lemma, normalize, script_ok

GOLD_SOURCES = frozenset({
    "wordnet",
    "omw-1.4",
    "wiktionary",
    "wiktextract",
    "wiktextract-multilingual",
    "wikidata",
})
GAP_CACHE_FILE = Path(__file__).resolve().parents[1] / "llm_gap_cache.json"

_LATIN_PRIMARY = frozenset({
    "es", "fr", "de", "pt", "id", "ms", "tr", "it", "nl", "pl",
    "cs", "sv", "da", "fi", "no", "hu", "ro", "sw", "en",
})


def gap_cache_key(synset_id: str, lang: str) -> str:
    return f"{synset_id}\t{lang}"


def load_gap_cache(path: Path = GAP_CACHE_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(k): str(v) for k, v in raw.items() if v}


def save_gap_cache(path: Path, cache: dict[str, str]) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def missing_rank_slots(
    ranked: set[tuple[str, str]],
    catalog_ids: list[str],
    langs: tuple[str, ...],
) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for synset_id in catalog_ids:
        for lang in langs:
            if lang == "en":
                continue
            if (synset_id, lang) not in ranked:
                missing.append((synset_id, lang))
    return missing


def accept_llm_lemma(lang: str, text: str) -> str | None:
    lemma = text.strip()
    if not is_usable_lemma(lemma) or not script_ok(lang, lemma):
        return None
    if lang not in _LATIN_PRIMARY and lemma.isascii():
        return None
    return lemma


def backtranslate_ok(proposed_en: str, synset_en_lemmas: set[str]) -> bool:
    folded = {normalize(item) for item in synset_en_lemmas}
    return normalize(proposed_en) in folded


def may_write_llm(existing_source: str | None) -> bool:
    return existing_source is None or existing_source not in GOLD_SOURCES
