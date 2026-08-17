from __future__ import annotations

import re

from schema import FUNCTION_WORDS, FUNCTION_WORDS_BY_LANG, SHORT_KEEP, WORDFREQ_LANG

LEMMA_RE = re.compile(r"^[^\W\d_][^\W\d_'-]*$", re.UNICODE)


def freq_lang(lang: str) -> str:
    return WORDFREQ_LANG.get(lang, lang)


def clean_lemma(raw: str) -> str:
    return raw.replace("_", " ").strip()


def normalize(text: str) -> str:
    return clean_lemma(text).casefold()


def is_usable_lemma(text: str) -> bool:
    return bool(text) and len(text) <= 40 and not any(ch.isdigit() for ch in text)


def _has_range(text: str, start: int, end: int) -> bool:
    return any(start <= ord(ch) <= end for ch in text)


def script_ok(lang: str, text: str) -> bool:
    if lang == "zh":
        return _has_range(text, 0x4E00, 0x9FFF)
    if lang == "ja":
        return _has_range(text, 0x3040, 0x30FF) or _has_range(text, 0x4E00, 0x9FFF)
    if lang == "ko":
        return _has_range(text, 0xAC00, 0xD7AF)
    if lang in {"ar", "fa", "ur"}:
        return _has_range(text, 0x0600, 0x06FF)
    if lang == "he":
        return _has_range(text, 0x0590, 0x05FF)
    if lang == "hi":
        return _has_range(text, 0x0900, 0x097F)
    if lang == "bn":
        return _has_range(text, 0x0980, 0x09FF)
    if lang == "ta":
        return _has_range(text, 0x0B80, 0x0BFF)
    if lang == "te":
        return _has_range(text, 0x0C00, 0x0C7F)
    if lang == "th":
        return _has_range(text, 0x0E00, 0x0E7F)
    if lang in {"ru", "uk"}:
        return _has_range(text, 0x0400, 0x04FF)
    if lang == "el":
        return _has_range(text, 0x0370, 0x03FF)
    return any(ch.isalpha() and ord(ch) < 0x300 for ch in text)


def is_function_word(lang: str, word: str) -> bool:
    folded = word.casefold()
    if lang == "en":
        if folded in FUNCTION_WORDS:
            return True
        if "'" in folded:
            return True
        if len(folded) < 3 and folded not in SHORT_KEEP:
            return True
        if not LEMMA_RE.match(folded):
            return True
    return folded in FUNCTION_WORDS_BY_LANG.get(lang, ())
