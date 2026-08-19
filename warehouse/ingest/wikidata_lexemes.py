from __future__ import annotations

import re

from schema import WIKT_CODE_TO_ISO, WORDNET_POS_TO_OURS
from warehouse.textutil import is_usable_lemma, script_ok

_P8814 = re.compile(r"^(\d{8})-([nvasr])$")


def parse_p8814(value: str) -> tuple[int, str] | None:
    match = _P8814.match(value.strip())
    if not match:
        return None
    pos = WORDNET_POS_TO_OURS.get(match.group(2))
    if pos is None:
        return None
    return int(match.group(1)), pos


def _claim_values(entity: dict, pid: str) -> list[str]:
    out: list[str] = []
    for claim in (entity.get("claims") or {}).get(pid) or []:
        snak = claim.get("mainsnak") or {}
        val = (snak.get("datavalue") or {}).get("value")
        if isinstance(val, str):
            out.append(val)
    return out


def wikidata_lexeme_links(
    entity: dict,
    offset_index: dict[tuple[int, str], str],
) -> list[tuple[str, str, str]]:
    if entity.get("type") != "lexeme":
        return []
    synset_ids: list[str] = []
    for raw in _claim_values(entity, "P8814"):
        parsed = parse_p8814(raw)
        if parsed is None:
            continue
        synset_id = offset_index.get(parsed)
        if synset_id:
            synset_ids.append(synset_id)
    if not synset_ids:
        return []
    links: list[tuple[str, str, str]] = []
    for lang_code, lemma_obj in (entity.get("lemmas") or {}).items():
        lang = WIKT_CODE_TO_ISO.get(lang_code)
        text = lemma_obj.get("value") if isinstance(lemma_obj, dict) else None
        if lang is None or lang == "en" or not isinstance(text, str):
            continue
        lemma = text.strip()
        if not is_usable_lemma(lemma) or not script_ok(lang, lemma):
            continue
        for synset_id in synset_ids:
            links.append((synset_id, lang, lemma))
    return links
