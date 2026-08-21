"""
warehouse/multilingual_compiler.py

High-precision 35-language translation and native gloss compiler.
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import Any

from schema import LANGUAGES
from warehouse.config import OUT_DIR
from warehouse.llm import call_chat_json, sanitize_candidate


def sanitize_translation_payload(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Sanitizes raw JSON translation output into clean string dictionaries."""
    cleaned: dict[str, dict[str, str]] = {}
    for word_or_cid, trans_map in payload.items():
        if not isinstance(trans_map, dict):
            continue
        cleaned_map: dict[str, str] = {}
        for lang, text in trans_map.items():
            if isinstance(text, list) and text:
                text = text[0]
            val = str(text or "").strip()
            if val:
                cleaned_map[str(lang)] = val
        if cleaned_map:
            cleaned[str(word_or_cid)] = cleaned_map
    return cleaned
