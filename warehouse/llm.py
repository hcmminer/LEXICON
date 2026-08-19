"""
warehouse/llm.py

OpenAI-compatible LLM client for offline dictionary curation.

Configuration is read from the environment or a local `.env` file
(git-ignored) so API keys are never committed:

    LEXICON_LLM_BASE_URL=http://localhost:20128/v1
    LEXICON_LLM_API_KEY=sk-...
    LEXICON_LLM_MODEL=ag/gemini-3.7-flash-high
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def llm_config() -> dict[str, str] | None:
    _load_dotenv()
    base_url = os.environ.get("LEXICON_LLM_BASE_URL", "").strip()
    api_key = os.environ.get("LEXICON_LLM_API_KEY", "").strip()
    model = os.environ.get("LEXICON_LLM_MODEL", "").strip()
    if not base_url or not api_key or not model:
        return None
    return {"base_url": base_url, "api_key": api_key, "model": model}


def save_llm_config(base_url: str, api_key: str, model: str) -> None:
    env_file = ROOT / ".env"
    existing: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            existing[key.strip()] = value.strip()
    existing["LEXICON_LLM_BASE_URL"] = base_url.strip()
    existing["LEXICON_LLM_API_KEY"] = api_key.strip()
    existing["LEXICON_LLM_MODEL"] = model.strip()
    lines = [f"{key}={value}\n" for key, value in existing.items()]
    env_file.write_text("".join(lines), encoding="utf-8")
    try:
        env_file.chmod(0o600)
    except OSError:
        pass


CURATION_SYSTEM_PROMPT = """You are a professional lexicographer for a language-learning app.
You are given one WordNet synset (a single sense/concept) with its English definition.
For each language, you will receive a list of candidate translations harvested automatically.

TASK: choose the single best, most natural, most precise translation for a learner in that
language. Rules:
- It must match THIS sense exactly (ignore unrelated senses the word may have).
- Prefer the most common everyday word a learner should know, but never a word that is
wrong or too obscure just to be "precise".
- Do NOT return function words, particles, or ambiguous short words unless truly correct.
- Return a JSON object: {"<lang>": "<chosen translation>"} for every requested language.
No extra text, no markdown fences."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_chat_json(
    system: str,
    user: str,
    *,
    retries: int = 3,
    backoff: float = 1.5,
    timeout: float = 60.0,
    temperature: float = 0.2,
    max_tokens: int = 65536,
) -> Any:
    """Call the configured LLM and parse a JSON response, with retry +
    exponential backoff + jitter. Raises RuntimeError on final failure.

    This is the single choke-point for all LLM traffic so retry policy is
    uniform (the Big-Tech batch-call pattern).
    """
    cfg = llm_config()
    if cfg is None:
        raise RuntimeError("LLM is not configured (LEXICON_LLM_BASE_URL/API_KEY/MODEL).")

    from openai import OpenAI

    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
    last_error: Exception | None = None
    attempt = 0
    while attempt <= retries:
        try:
            response = client.chat.completions.create(
                model=cfg["model"],
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                timeout=timeout,
                max_tokens=max_tokens,
            )
            content = (response.choices[0].message.content or "").strip()
            return json.loads(_strip_fences(content))
        except Exception as exc:  # noqa: BLE001 - includes rate-limit, JSON parse, network
            last_error = exc
            attempt += 1
            if attempt > retries:
                break
            import random
            import time

            time.sleep(backoff * (2 ** (attempt - 1)) * (0.7 + 0.6 * random.random()))
    raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last_error}")


def pick_best_translations(
    synset_id: str,
    pos: str,
    meaning: str,
    candidates: dict[str, list[str]],
    timeout: float = 60.0,
) -> dict[str, str]:
    """Ask the LLM to pick the best translation per language for one synset."""
    prompt_lines = [
        f"Synset: {synset_id}",
        f"POS: {pos}",
        f"Definition (EN): {meaning}",
        "",
        "Candidates:",
    ]
    for lang, words in candidates.items():
        prompt_lines.append(f"- {lang}: {', '.join(words) if words else '(none)'}")
    prompt_lines.append("")
    prompt_lines.append("Return only the JSON object now.")

    payload = call_chat_json(CURATION_SYSTEM_PROMPT, "\n".join(prompt_lines), timeout=timeout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected LLM payload for {synset_id}: {payload}")
    return {str(k): str(v) for k, v in payload.items() if isinstance(v, str) and v.strip()}


def sanitize_candidate(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []
