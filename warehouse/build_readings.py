from __future__ import annotations

from phonology import system_ids_for
from warehouse.readings_extra import indic, latin_ipa, semitic, thai, vietnamese_ipa


class _Engines:
    kakasi = None
    ipa_ok = True


_CACHE: dict[tuple[str, str], dict[str, str]] = {}

_ISO9_BASE = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "ë",
    "ж": "ž",
    "з": "z",
    "и": "i",
    "й": "j",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "č",
    "ш": "š",
    "щ": "ŝ",
    "ъ": "ʺ",
    "ы": "y",
    "ь": "ʹ",
    "э": "è",
    "ю": "û",
    "я": "â",
}
_ISO9_UK = {
    **_ISO9_BASE,
    "є": "ê",
    "і": "ì",
    "ї": "ï",
    "ґ": "g̀",
}
_ELOT743 = {
    "α": "a",
    "β": "v",
    "γ": "g",
    "δ": "d",
    "ε": "e",
    "ζ": "z",
    "η": "i",
    "θ": "th",
    "ι": "i",
    "κ": "k",
    "λ": "l",
    "μ": "m",
    "ν": "n",
    "ξ": "x",
    "ο": "o",
    "π": "p",
    "ρ": "r",
    "σ": "s",
    "ς": "s",
    "τ": "t",
    "υ": "y",
    "φ": "f",
    "χ": "ch",
    "ψ": "ps",
    "ω": "o",
    "ά": "á",
    "έ": "é",
    "ή": "í",
    "ί": "í",
    "ό": "ó",
    "ύ": "ý",
    "ώ": "ó",
    "ϊ": "ï",
    "ϋ": "ÿ",
}


def readings_for(lang: str, text: str) -> dict[str, str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {}
    cache_key = (lang, cleaned)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)
    try:
        allowed = system_ids_for(lang)
    except KeyError:
        return {}
    raw = _generate(lang, cleaned)
    filtered = {
        key: value
        for key, value in raw.items()
        if key in allowed and value and value != cleaned
    }
    _CACHE[cache_key] = filtered
    return dict(filtered)


def _generate(lang: str, text: str) -> dict[str, str]:
    if lang == "zh":
        return _zh(text)
    if lang == "ja":
        return _ja(text)
    if lang == "ko":
        return _ko(text)
    if lang == "en":
        return _en(text)
    if lang == "ru":
        return _map_script(text, _ISO9_BASE, "iso9")
    if lang == "uk":
        return _map_script(text, _ISO9_UK, "iso9")
    if lang == "el":
        return _map_script(text, _ELOT743, "elot743")
    if lang == "vi":
        return vietnamese_ipa(text)
    if lang in {"hi", "bn", "ta", "te"}:
        return indic(lang, text)
    if lang in {"ar", "fa", "ur", "he"}:
        return semitic(lang, text)
    if lang == "th":
        return thai(text)
    if lang in {
        "es",
        "fr",
        "de",
        "pt",
        "id",
        "ms",
        "tr",
        "it",
        "nl",
        "pl",
        "cs",
        "sv",
        "da",
        "fi",
        "no",
        "hu",
        "ro",
        "sw",
    }:
        return latin_ipa(lang, text)
    return {}


def _map_script(text: str, table: dict[str, str], system: str) -> dict[str, str]:
    rendered = "".join(table.get(char, table.get(char.lower(), char)) for char in text)
    folded = rendered.casefold()
    source = text.casefold()
    if not folded or folded == source:
        return {}
    return {system: folded}


def _zh(text: str) -> dict[str, str]:
    try:
        from pypinyin import Style, pinyin
    except ImportError:
        return {}
    out: dict[str, str] = {}
    tone = " ".join(part[0] for part in pinyin(text, style=Style.TONE) if part).strip()
    if tone and tone != text:
        out["pinyin"] = tone
    bopo = " ".join(part[0] for part in pinyin(text, style=Style.BOPOMOFO) if part).strip()
    if bopo and bopo != text:
        out["zhuyin"] = bopo
    return out


def _ja(text: str) -> dict[str, str]:
    if _Engines.kakasi is None:
        try:
            import pykakasi

            _Engines.kakasi = pykakasi.kakasi()
        except ImportError:
            _Engines.kakasi = False
    if _Engines.kakasi is False:
        return {}
    converted = _Engines.kakasi.convert(text)
    hiragana = "".join(item.get("hira", "") for item in converted)
    romaji = "".join(item.get("hepburn", "") for item in converted).strip()
    out: dict[str, str] = {}
    if hiragana and hiragana != text:
        out["hiragana"] = hiragana
    if romaji and romaji != text:
        out["romaji"] = romaji
    return out


def _ko(text: str) -> dict[str, str]:
    try:
        from korean_romanizer.romanizer import Romanizer
    except ImportError:
        return {}
    try:
        romanized = Romanizer(text).romanize()
    except Exception:
        return {}
    return {"rr": romanized} if romanized and romanized != text else {}


def _en(text: str) -> dict[str, str]:
    if not _Engines.ipa_ok or " " in text:
        return {}
    try:
        import eng_to_ipa as ipa
    except ImportError:
        _Engines.ipa_ok = False
        return {}
    try:
        rendered = ipa.convert(text)
    except Exception:
        return {}
    if not rendered or rendered.endswith("*") or rendered == text:
        folded = text.casefold()
        return {"ipa": f"/{folded}/"} if folded.isascii() and any(ch.isalpha() for ch in folded) else {}
    return {"ipa": f"/{rendered}/"}
