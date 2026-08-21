from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phonology import system_ids_for
from schema import LANGUAGES, SCHEMA_VERSION, SOURCES, WORDNET_POS_TO_OURS, empty_envelope
from warehouse.config import OUT_DIR
from warehouse.db import connect
from warehouse.gloss_generator import load_gloss_cache
from warehouse.textutil import is_function_word, is_usable_lemma, lemma_text
import wordfreq
from validate import validate_document, write_coverage


def _term_from_row(row: dict[str, Any]) -> dict[str, Any]:
    term: dict[str, Any] = {"text": row["text"], "rank": int(row["rank"])}
    allowed = system_ids_for(row["lang"])
    readings = {
        key: value
        for key, value in dict(row["readings"] or {}).items()
        if key in allowed and value
    }
    if readings:
        term["readings"] = readings
    return term


def _fetch_rows(pivot: str | None, top_n: int) -> list[dict[str, Any]]:
    with connect() as conn:
        if pivot:
            return conn.execute(
                """
                SELECT
                    s.id AS synset_id,
                    s.pos,
                    s.definition_en,
                    cr.lang,
                    cr.rank,
                    l.text,
                    (
                        SELECT jsonb_object_agg(r.system, r.value)
                        FROM core.readings r
                        WHERE r.lemma_id = l.id
                    ) AS readings
                FROM core.concept_ranks cr
                JOIN core.synsets s ON s.id = cr.synset_id
                JOIN core.lemmas l ON l.id = cr.lemma_id
                WHERE cr.synset_id IN (
                    SELECT synset_id FROM core.concept_ranks
                    WHERE lang = %s AND rank <= %s
                )
                ORDER BY s.id, cr.lang
                """,
                (pivot, top_n),
            ).fetchall()
        return conn.execute(
            """
            SELECT
                s.id AS synset_id,
                s.pos,
                s.definition_en,
                cr.lang,
                cr.rank,
                l.text,
                (
                    SELECT jsonb_object_agg(r.system, r.value)
                    FROM core.readings r
                    WHERE r.lemma_id = l.id
                ) AS readings
            FROM core.concept_ranks cr
            JOIN core.synsets s ON s.id = cr.synset_id
            JOIN core.lemmas l ON l.id = cr.lemma_id
            ORDER BY s.id, cr.lang
            """
        ).fetchall()


def _load_curated_overrides() -> dict[str, dict[str, str]]:
    overrides_file = Path(__file__).parent / "curated_overrides.json"
    if overrides_file.exists():
        try:
            return json.loads(overrides_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def build_catalog(
    top_n: int = 12000,
    pivot: str | None = None,
    target_langs: list[str] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    selected_langs = set(target_langs) if target_langs else set(LANGUAGES)
    if pivot:
        selected_langs.add(pivot)

    from validate import validate_document, write_coverage

    overrides = _load_curated_overrides()
    gloss_cache = load_gloss_cache()

    for row in _fetch_rows(pivot, top_n):
        if row["lang"] not in selected_langs:
            continue
        concept = grouped.setdefault(
            row["synset_id"],
            {
                "id": row["synset_id"],
                "pos": WORDNET_POS_TO_OURS.get(row["pos"], "other"),
                "meaning": row["definition_en"],
                "terms": {},
            },
        )
        term = _term_from_row(row)
        # Populate localized meaning if present in gloss cache
        if row["synset_id"] in gloss_cache and row["lang"] in gloss_cache[row["synset_id"]]:
            term["meaning"] = gloss_cache[row["synset_id"]][row["lang"]]
        concept["terms"][row["lang"]] = term

    # Apply curated overrides (both updating existing and filling missing verified terms)
    for synset_id, override_terms in overrides.items():
        if synset_id in grouped:
            concept = grouped[synset_id]
            for lang, text in override_terms.items():
                if lang in selected_langs and is_usable_lemma(lemma_text(text)) and not is_function_word(lang, text):
                    if lang in concept["terms"]:
                        concept["terms"][lang]["text"] = text
                    else:
                        concept["terms"][lang] = {"text": text, "rank": 99999}

    if pivot:
        concepts = [item for item in grouped.values() if pivot in item["terms"]]
        by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for concept in concepts:
            for lang, term in concept["terms"].items():
                by_lang[lang].append(term)
        for lang, terms in by_lang.items():
            terms.sort(key=lambda term: (term.get("rank", 99999), term["text"]))
            for rank, term in enumerate(terms, start=1):
                term["rank"] = rank
        concepts.sort(key=lambda item: (item["terms"][pivot]["rank"], item["id"]))
    else:
        concepts = [
            item
            for item in grouped.values()
            if "en" in item["terms"] and len(item["terms"]) >= 2
        ]
        by_lang: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for concept in concepts:
            for lang, term in concept["terms"].items():
                by_lang[lang].append(term)
        for lang, terms in by_lang.items():
            if lang == "en":
                terms.sort(key=lambda term: (
                    -wordfreq.zipf_frequency(term["text"], "en") if wordfreq.zipf_frequency(term["text"], "en") > 0 else 99999,
                    term.get("rank", 99999),
                    term["text"]
                ))
            else:
                terms.sort(key=lambda term: (term.get("rank", 99999), term["text"]))
            for rank, term in enumerate(terms, start=1):
                term["rank"] = rank
        concepts.sort(key=lambda item: (item["terms"]["en"]["rank"], item["id"]))

    catalog = empty_envelope(len(concepts), top_n, pivot)
    catalog["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    catalog["version"] = SCHEMA_VERSION
    catalog["sources"] = list(SOURCES)
    catalog["languages"] = [lang for lang in LANGUAGES if lang in selected_langs]
    catalog["phonology"] = {
        lang: catalog["phonology"][lang]
        for lang in catalog["languages"]
        if lang in catalog["phonology"]
    }
    catalog["concepts"] = concepts
    return catalog


def export_json(
    out_dir: Path | None = None,
    top_n: int = 12000,
    pivot: str | None = None,
    target_langs: list[str] | None = None,
) -> Path:
    dest_dir = out_dir or OUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog(top_n=top_n, pivot=pivot, target_langs=target_langs)
    stem = f"core_vocabulary.{pivot}-{top_n}" if pivot else "core_vocabulary"
    path = dest_dir / f"{stem}.json"
    payload = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    with gzip.open(dest_dir / f"{stem}.json.gz", "wt", encoding="utf-8") as handle:
        handle.write(payload)
    warnings, coverage = validate_document(catalog)
    write_coverage(dest_dir / f"{stem}.coverage.json", coverage, catalog["count"])
    for warning in warnings:
        print(f"WARN {warning}")
    print(f"exported {path} concepts={catalog['count']}")
    return path
