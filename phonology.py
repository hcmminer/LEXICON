from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PronunciationSystem:
    id: str
    label: str
    script: str
    learner: bool


def _s(system_id: str, label: str, script: str, learner: bool = False) -> PronunciationSystem:
    return PronunciationSystem(system_id, label, script, learner)


IPA = _s("ipa", "IPA", "ipa", True)

_LATIN_IPA = (IPA,)

LANGUAGE_PHONOLOGY: dict[str, tuple[PronunciationSystem, ...]] = {
    "en": (
        _s("ipa", "IPA", "ipa", True),
        _s("ipa-us", "IPA (General American)", "ipa", False),
        _s("ipa-gb", "IPA (Received Pronunciation)", "ipa", False),
    ),
    "vi": (
        _s("ipa", "IPA", "ipa", True),
    ),
    "zh": (
        _s("pinyin", "Hanyu Pinyin", "latn", True),
        _s("zhuyin", "Zhuyin / Bopomofo", "bopo", False),
        _s("ipa", "IPA", "ipa", False),
    ),
    "ja": (
        _s("hiragana", "Hiragana", "hira", True),
        _s("romaji", "Hepburn romaji", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "ko": (
        _s("rr", "Revised Romanization", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "hi": (
        _s("iast", "IAST", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "es": _LATIN_IPA,
    "fr": _LATIN_IPA,
    "de": _LATIN_IPA,
    "pt": _LATIN_IPA,
    "ru": (
        _s("iso9", "ISO 9 romanization", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "ar": (
        _s("alalc", "ALA-LC romanization", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "bn": (
        _s("iso15919", "ISO 15919", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "id": _LATIN_IPA,
    "ms": _LATIN_IPA,
    "th": (
        _s("rtgs", "Royal Thai General System", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "tr": _LATIN_IPA,
    "it": _LATIN_IPA,
    "nl": _LATIN_IPA,
    "pl": _LATIN_IPA,
    "uk": (
        _s("iso9", "ISO 9 romanization", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "el": (
        _s("elot743", "ELOT 743 romanization", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "cs": _LATIN_IPA,
    "sv": _LATIN_IPA,
    "da": _LATIN_IPA,
    "fi": _LATIN_IPA,
    "no": _LATIN_IPA,
    "hu": _LATIN_IPA,
    "ro": _LATIN_IPA,
    "he": (
        _s("alalc", "ALA-LC romanization", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "fa": (
        _s("un", "UN romanization", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "ur": (
        _s("alalc", "ALA-LC romanization", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "ta": (
        _s("iso15919", "ISO 15919", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "te": (
        _s("iso15919", "ISO 15919", "latn", True),
        _s("ipa", "IPA", "ipa", False),
    ),
    "sw": _LATIN_IPA,
}


def _assert_complete() -> None:
    for code, systems in LANGUAGE_PHONOLOGY.items():
        if not systems:
            raise RuntimeError(f"{code} has no pronunciation systems")
        ids = [item.id for item in systems]
        if len(ids) != len(set(ids)):
            raise RuntimeError(f"{code} has duplicate system ids")
        if not any(item.learner for item in systems):
            raise RuntimeError(f"{code} needs at least one learner system")


_assert_complete()


def systems_for(lang: str) -> tuple[PronunciationSystem, ...]:
    return LANGUAGE_PHONOLOGY[lang]


def system_ids_for(lang: str) -> frozenset[str]:
    return frozenset(item.id for item in LANGUAGE_PHONOLOGY[lang])


def phonology_dto(order: tuple[str, ...] | None = None) -> dict[str, dict[str, list[dict[str, object]]]]:
    keys = order if order is not None else tuple(LANGUAGE_PHONOLOGY)
    return {
        lang: {"systems": [asdict(item) for item in LANGUAGE_PHONOLOGY[lang]]}
        for lang in keys
    }
