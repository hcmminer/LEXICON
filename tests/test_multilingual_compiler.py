# /Users/admin/Documents/big-data/tests/test_multilingual_compiler.py
from warehouse.multilingual_compiler import sanitize_translation_payload

def test_sanitize_translation_payload():
    payload = {
        "water": {"vi": "nước", "zh": "水", "ja": "水", "es": "agua"},
        "learn": {"vi": "học", "zh": "学习", "ja": "学ぶ", "es": "aprender"}
    }
    cleaned = sanitize_translation_payload(payload)
    assert cleaned["water"]["vi"] == "nước"
    assert cleaned["learn"]["vi"] == "học"
