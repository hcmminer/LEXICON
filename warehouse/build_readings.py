from __future__ import annotations


class _Engines:
    kakasi = None
    ipa_ok = True


def readings_for(lang: str, text: str) -> dict[str, str]:
    if lang == "zh":
        return _zh(text)
    if lang == "ja":
        return _ja(text)
    if lang == "ko":
        return _ko(text)
    if lang == "en":
        return _en(text)
    return {}


def _zh(text: str) -> dict[str, str]:
    try:
        from pypinyin import Style, pinyin
    except ImportError:
        return {}
    out: dict[str, str] = {}
    tone = "".join(part[0] for part in pinyin(text, style=Style.TONE) if part)
    if tone:
        out["pinyin"] = tone
    bopo = "".join(part[0] for part in pinyin(text, style=Style.BOPOMOFO) if part)
    if bopo:
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
    if romaji:
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
        return {}
    return {"ipa": f"/{rendered}/"}
