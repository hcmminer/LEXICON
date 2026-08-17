from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1
SOURCES = ("wordfreq", "omw-1.4", "wiktextract")

LANGUAGES: tuple[str, ...] = (
    "en",
    "vi",
    "zh",
    "ja",
    "ko",
    "hi",
    "es",
    "fr",
    "de",
    "pt",
    "ru",
    "ar",
    "bn",
    "id",
    "ms",
    "th",
    "tr",
    "it",
    "nl",
    "pl",
    "uk",
    "el",
    "cs",
    "sv",
    "da",
    "fi",
    "no",
    "hu",
    "ro",
    "he",
    "fa",
    "ur",
    "ta",
    "te",
    "sw",
)

POS_VALUES = frozenset({"noun", "verb", "adjective", "adverb", "phrase", "other"})

WORDNET_POS_TO_OURS = {
    "n": "noun",
    "v": "verb",
    "a": "adjective",
    "s": "adjective",
    "r": "adverb",
}

OMW_LANG_TO_ISO = {
    "cmn": "zh",
    "jpn": "ja",
    "spa": "es",
    "fra": "fr",
    "arb": "ar",
    "ind": "id",
    "zsm": "ms",
    "tha": "th",
    "ita": "it",
    "nld": "nl",
    "pol": "pl",
    "ell": "el",
    "swe": "sv",
    "dan": "da",
    "fin": "fi",
    "nob": "no",
    "heb": "he",
    "por": "pt",
    "ron": "ro",
}

WIKT_CODE_TO_ISO = {
    "en": "en",
    "vi": "vi",
    "zh": "zh",
    "zh-Hans": "zh",
    "zh-CN": "zh",
    "cmn": "zh",
    "ja": "ja",
    "ko": "ko",
    "hi": "hi",
    "es": "es",
    "fr": "fr",
    "de": "de",
    "pt": "pt",
    "pt-BR": "pt",
    "ru": "ru",
    "ar": "ar",
    "bn": "bn",
    "id": "id",
    "ms": "ms",
    "zsm": "ms",
    "th": "th",
    "tr": "tr",
    "it": "it",
    "nl": "nl",
    "pl": "pl",
    "uk": "uk",
    "el": "el",
    "cs": "cs",
    "sv": "sv",
    "da": "da",
    "fi": "fi",
    "no": "no",
    "nb": "no",
    "nn": "no",
    "hu": "hu",
    "ro": "ro",
    "he": "he",
    "fa": "fa",
    "ur": "ur",
    "ta": "ta",
    "te": "te",
    "sw": "sw",
}

WIKT_POS_TO_OURS = {
    "noun": "noun",
    "verb": "verb",
    "adj": "adjective",
    "adjective": "adjective",
    "adv": "adverb",
    "adverb": "adverb",
    "phrase": "phrase",
    "prep": "other",
    "pron": "other",
    "conj": "other",
    "intj": "other",
    "det": "other",
    "num": "other",
    "particle": "other",
}

FUNCTION_WORDS_BY_LANG = {
    "vi": frozenset(
        """
        là thì mà của và hoặc nhưng nếu vì để được bị các những
        này đó kia ấy đã sẽ đang chưa không chẳng rất quá cũng vẫn
        hãy nhé thôi với về trong ngoài trên dưới một tôi mình bạn
        ta chúng người cái sự việc ở tại bằng như còn lại
        """.split()
    ),
    "zh": frozenset("的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 自己 这".split()),
    "de": frozenset("der die das den dem des ein eine einer eines und oder aber wenn weil mit von zu im am".split()),
    "ko": frozenset("이 그 저 것 수 등 때 및 또 또는 그리고 그러나 그래서 이다 있다 없다 하다".split()),
}

SHORT_KEEP = frozenset({"go"})

FUNCTION_WORDS = frozenset(
    """
    a an the this that these those
    i me my mine myself we us our ours ourselves
    you your yours yourself yourselves
    he him his himself she her hers herself
    it its itself they them their theirs themselves
    who whom whose which what
    be am is are was were been being
    have has had having
    do does did doing done
    will would shall should can could may might must
    of to in on for and or but if as at by from with
    about into over after before under between through
    during without within against among
    not no nor none never
    so than then there here when where how why
    all each every both few more most other some such
    only own same too very just also even still
    yes ok
    one two three four five
    like up out off down again once here there now then
    any much many get
    """.split()
)

WORDFREQ_LANG = {
    "no": "nb",
}

SYNSET_ID_RE = r"^.+\.[nvasr]\.\d{2}$"

from phonology import LANGUAGE_PHONOLOGY, phonology_dto

if set(LANGUAGE_PHONOLOGY) != set(LANGUAGES):
    raise RuntimeError("phonology registry languages do not match LANGUAGES")


def empty_envelope(count: int = 0, top_n: int = 0, pivot: str | None = None) -> dict[str, Any]:
    envelope = {
        "version": SCHEMA_VERSION,
        "generatedAt": "",
        "sources": list(SOURCES),
        "languages": list(LANGUAGES),
        "phonology": phonology_dto(LANGUAGES),
        "topN": top_n,
        "count": count,
        "concepts": [],
    }
    if pivot:
        envelope["pivot"] = pivot
    return envelope
