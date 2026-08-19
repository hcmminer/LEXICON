"""
warehouse/gloss_generator.py

Generates localized natural definitions (glosses/meanings) for concept terms
across 35 languages using LLM-assisted translation, and persists them into a
gloss cache (warehouse/glosses_cache.json).

Two entry points:
  * generate_missing_glosses(...)       - one concept, one request
  * generate_missing_glosses_batch(...) - several concepts, one request
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from warehouse.llm import call_chat_json, llm_config

GLOSS_CACHE_FILE = Path(__file__).parent / "glosses_cache.json"


def load_gloss_cache() -> dict[str, dict[str, str]]:
    if GLOSS_CACHE_FILE.exists():
        try:
            return json.loads(GLOSS_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_gloss_cache(cache: dict[str, dict[str, str]]) -> None:
    payload = json.dumps(cache, ensure_ascii=False, indent=2) + "\n"
    GLOSS_CACHE_FILE.write_text(payload, encoding="utf-8")


def _strip_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return content.strip()


def _client():
    from openai import OpenAI

    cfg = llm_config()
    if not cfg:
        raise RuntimeError("LLM not configured (LEXICON_LLM_BASE_URL/API_KEY/MODEL).")
    return OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"]), cfg["model"]


def generate_missing_glosses(
    concept_id: str,
    pos: str,
    definition_en: str,
    terms: dict[str, dict[str, Any]],
    target_langs: list[str] | None = None,
) -> dict[str, str]:
    """Localized glosses for ONE concept's terms (one LLM request)."""
    langs_to_generate = (target_langs or list(terms.keys())) or []
    if not langs_to_generate:
        return {}
    prompt = (
        "Translate the short English definition below into every requested language. "
        "Write each definition natively in that language — never keep English.\n\n"
        f"Concept: {concept_id}\nPOS: {pos}\nEnglish definition: {definition_en}\n\n"
        "Words:\n"
        + "\n".join(f"- {l}: {terms.get(l, {}).get('text', '')}" for l in langs_to_generate)
        + '\n\nReturn ONLY JSON: {"<lang>": "<definition>"} (each ≤ 10 words).'
    )
    data = call_chat_json(
        "You are a professional multilingual dictionary gloss writer. Output strict JSON.",
        prompt,
        retries=3,
        backoff=1.5,
        timeout=40.0,
    )
    if not isinstance(data, dict):
        raise ValueError(f"LLM returned non-object for {concept_id}")
    result: dict[str, str] = {}
    for lang, gloss in data.items():
        if isinstance(gloss, str) and gloss.strip():
            result[str(lang)] = gloss.strip()
    return result


def generate_missing_glosses_batch(
    concepts: list[dict[str, Any]],
    langs: list[str] | None = None,
    timeout: float = 180.0,
) -> dict[str, dict[str, str]]:
    """Localized glosses for SEVERAL concepts in ONE LLM request.

    `concepts` is a list of {id, pos, meaning, terms}. `terms` should already
    be filtered to *missing* langs only. Returns {concept_id: {lang: gloss}}.
    """
    if not concepts:
        return {}
    wanted = set(langs) if langs else None
    lines = [
        "Translate the short English definition of each concept into every listed language. "
        "Write each definition natively in that language — never keep English. "
        "Skip English itself. Return every listed language — do not drop any.",
        "",
    ]
    for c in concepts:
        lines.append(f"### {c['id']} | pos={c.get('pos','')} | EN: {c.get('meaning','')}")
        for lang, term in (c.get("terms") or {}).items():
            if wanted is not None and lang not in wanted:
                continue
            if lang == "en":
                continue
            lines.append(f"  [{lang}] {term.get('text','')}")
    lines.append("")
    lines.append(
        'Return ONLY a JSON object: {"<concept_id>": {"<lang>": "<definition>"}}. '
        "Each definition is one short natural sentence (max 10 words)."
    )
    data = call_chat_json(
        "You are a professional multilingual dictionary gloss writer. Output strict JSON.",
        "\n".join(lines),
        retries=3,
        backoff=1.5,
        timeout=timeout,
        max_tokens=65536,
    )
    if not isinstance(data, dict):
        raise ValueError(f"LLM returned non-object: {str(data)[:120]}")
    result: dict[str, dict[str, str]] = {}
    for cid, glosses in data.items():
        if not isinstance(glosses, dict):
            continue
        clean = {
            str(k): str(v).strip()
            for k, v in glosses.items()
            if isinstance(v, str) and v.strip()
        }
        if clean:
            result[str(cid)] = clean
    return result
