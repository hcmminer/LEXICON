from __future__ import annotations

from schema import FUNCTION_WORDS, FUNCTION_WORDS_BY_LANG, LANGUAGES
from warehouse.db import connect, executemany
from warehouse.textutil import freq_lang, normalize


def seed_reference_data() -> None:
    from wordfreq import available_languages

    available = set(available_languages())
    rows = []
    for code in LANGUAGES:
        wf = freq_lang(code)
        rows.append((code, wf, wf in available))

    function_rows = [("en", normalize(word)) for word in FUNCTION_WORDS]
    for lang, words in FUNCTION_WORDS_BY_LANG.items():
        function_rows.extend((lang, normalize(word)) for word in words)

    with connect() as conn:
        executemany(conn,
            """
            INSERT INTO core.languages (code, wordfreq_code, has_wordlist)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO UPDATE
            SET wordfreq_code = EXCLUDED.wordfreq_code,
                has_wordlist = EXCLUDED.has_wordlist
            """,
            rows,
        )
        executemany(conn,
            """
            INSERT INTO core.function_words (lang, normalized)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            function_rows,
        )
        conn.commit()
    print(f"seeded {len(rows)} languages, {len(function_rows)} function words")
