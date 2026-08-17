from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from schema import LANGUAGES, READING_KEYS, SCHEMA_VERSION, SOURCES, WORDNET_POS_TO_OURS, empty_envelope
from warehouse.config import OUT_DIR
from warehouse.db import connect
from validate import validate_document, write_coverage


def export_json(out_dir: Path | None = None, top_n: int = 12000) -> Path:
    dest_dir = out_dir or OUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        rows = conn.execute(
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

    grouped: dict[str, dict] = {}
    for row in rows:
        concept = grouped.setdefault(
            row["synset_id"],
            {
                "id": row["synset_id"],
                "pos": WORDNET_POS_TO_OURS.get(row["pos"], "other"),
                "meaning": row["definition_en"],
                "terms": {},
            },
        )
        term = {"text": row["text"], "rank": int(row["rank"])}
        readings = row["readings"] or {}
        if readings:
            term["readings"] = dict(readings)
        concept["terms"][row["lang"]] = term

    concepts = [
        item
        for item in grouped.values()
        if "en" in item["terms"] and len(item["terms"]) >= 2
    ]
    concepts.sort(key=lambda item: (item["terms"]["en"]["rank"], item["id"]))

    catalog = empty_envelope(len(concepts), top_n)
    catalog["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    catalog["version"] = SCHEMA_VERSION
    catalog["sources"] = list(SOURCES)
    catalog["languages"] = list(LANGUAGES)
    catalog["readingKeys"] = list(READING_KEYS)
    catalog["concepts"] = concepts

    path = dest_dir / "core_vocabulary.json"
    payload = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    with gzip.open(dest_dir / "core_vocabulary.json.gz", "wt", encoding="utf-8") as handle:
        handle.write(payload)
    warnings, coverage = validate_document(catalog)
    write_coverage(dest_dir / "coverage.json", coverage, catalog["count"])
    for warning in warnings:
        print(f"WARN {warning}")
    print(f"exported {path} concepts={catalog['count']}")
    return path
