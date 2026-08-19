from __future__ import annotations

from schema import WIKT_CODE_TO_ISO, WIKT_POS_TO_OURS
from warehouse.textutil import is_usable_lemma, normalize, script_ok

OURS_TO_WN = {"noun": ("n",), "verb": ("v",), "adjective": ("a", "s"), "adverb": ("r",)}


def _english_words(entry: dict) -> list[str]:
    found: list[str] = []
    buckets = []
    if isinstance(entry.get("translations"), list):
        buckets.append(entry["translations"])
    for sense in entry.get("senses") or []:
        if isinstance(sense, dict) and isinstance(sense.get("translations"), list):
            buckets.append(sense["translations"])
    for group in buckets:
        for item in group:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or item.get("lang_code") or "")
            if WIKT_CODE_TO_ISO.get(code) != "en":
                continue
            word = item.get("word")
            if isinstance(word, str) and word.strip():
                found.append(word.strip())
    return found


def native_entry_links(entry: dict, en_index: dict[tuple[str, str], list[str]]) -> list[tuple[str, str, str]]:
    lemma = str(entry.get("word") or "").strip()
    lang = WIKT_CODE_TO_ISO.get(str(entry.get("lang_code") or ""))
    pos = WIKT_POS_TO_OURS.get(str(entry.get("pos") or ""))
    if not lemma or lang is None or lang == "en" or pos is None:
        return []
    if not is_usable_lemma(lemma) or not script_ok(lang, lemma):
        return []
    pos_keys = (pos, *OURS_TO_WN.get(pos, ()))
    links: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for en in _english_words(entry):
        folded = normalize(en)
        if folded == normalize(lemma):
            continue
        for pos_key in pos_keys:
            for synset_id in en_index.get((folded, pos_key), [])[:3]:
                if synset_id not in seen:
                    seen.add(synset_id)
                    links.append((synset_id, lang, lemma))
    return links
