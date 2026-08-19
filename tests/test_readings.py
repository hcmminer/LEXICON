from __future__ import annotations

from phonology import LANGUAGE_PHONOLOGY, system_ids_for
from warehouse.build_readings import readings_for


def test_reading_keys_are_registered_systems() -> None:
    samples = {
        "en": "apple",
        "zh": "你好",
        "ja": "学校",
        "ko": "안녕",
        "ru": "спасибо",
        "uk": "дякую",
        "el": "ευχαριστώ",
        "vi": "xin chào",
    }
    for lang, text in samples.items():
        readings = readings_for(lang, text)
        allowed = system_ids_for(lang)
        assert set(readings).issubset(allowed), f"{lang}: {set(readings) - allowed}"


def test_chinese_learner_pinyin() -> None:
    readings = readings_for("zh", "你好")
    assert "pinyin" in readings
    assert readings["pinyin"]


def test_japanese_learner_kana_or_romaji() -> None:
    readings = readings_for("ja", "学校")
    assert "hiragana" in readings or "romaji" in readings


def test_korean_revised_romanization() -> None:
    readings = readings_for("ko", "안녕")
    assert readings.get("rr")


def test_english_ipa_wrapped() -> None:
    readings = readings_for("en", "apple")
    assert readings["ipa"].startswith("/")
    assert readings["ipa"].endswith("/")


def test_russian_iso9() -> None:
    readings = readings_for("ru", "спасибо")
    assert readings["iso9"] == "spasibo"


def test_unknown_language_returns_empty() -> None:
    assert readings_for("xx", "word") == {}


def test_phonology_covers_all_registry_languages() -> None:
    assert set(LANGUAGE_PHONOLOGY) >= {
        "en",
        "vi",
        "zh",
        "ja",
        "ko",
        "ru",
        "el",
        "uk",
    }


LEARNER_SAMPLES: dict[str, str] = {
    "en": "apple",
    "vi": "nước",
    "zh": "你好",
    "ja": "学校",
    "ko": "안녕",
    "hi": "हम",
    "es": "muy",
    "fr": "bonjour",
    "de": "schon",
    "pt": "quando",
    "ru": "спасибо",
    "ar": "يوم",
    "bn": "কাজ",
    "id": "sekolah",
    "ms": "sekolah",
    "th": "ร้าง",
    "tr": "böyle",
    "it": "essere",
    "nl": "meer",
    "pl": "jeszcze",
    "uk": "дякую",
    "el": "ευχαριστώ",
    "cs": "první",
    "sv": "får",
    "da": "godt",
    "fi": "mukaan",
    "no": "ha",
    "hu": "nagy",
    "ro": "poate",
    "he": "לפני",
    "fa": "اما",
    "ur": "ساتھ",
    "ta": "இந்திய",
    "te": "దాదాపు",
    "sw": "uwezo",
}


def test_every_shipped_language_emits_a_learner_reading() -> None:
    assert set(LEARNER_SAMPLES) == set(LANGUAGE_PHONOLOGY)
    for lang, text in LEARNER_SAMPLES.items():
        readings = readings_for(lang, text)
        learner_ids = [item.id for item in LANGUAGE_PHONOLOGY[lang] if item.learner]
        assert readings, f"{lang} produced no readings for {text!r}"
        assert any(system in readings for system in learner_ids), f"{lang}: {readings} missing {learner_ids}"
        assert set(readings).issubset(system_ids_for(lang))


def test_vietnamese_ipa_is_wrapped() -> None:
    readings = readings_for("vi", "nước")
    assert readings["ipa"].startswith("/")
    assert readings["ipa"].endswith("/")


def test_hindi_iast_is_latin() -> None:
    readings = readings_for("hi", "हम")
    assert readings["iast"]
    assert readings["iast"].isascii() or all(ord(ch) < 0x0300 or ch in "āīūṛṝḷḹṃḥñṭḍṇśṣ" for ch in readings["iast"])
